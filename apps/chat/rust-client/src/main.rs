use chat_rust::{protocol, state, terminal, transport};
use state::{ClientState, ConnectionState, SessionState};
use terminal::Command;

enum Action {
    Input(Option<std::io::Result<String>>),
    Connected(Result<transport::Connection, String>),
    Network(Result<transport::Event, String>),
}

fn url() -> Result<String, &'static str> {
    let mut arguments = std::env::args().skip(1);
    match (
        arguments.next().as_deref(),
        arguments.next(),
        arguments.next(),
    ) {
        (Some("--url"), Some(url), None) => Ok(url),
        _ => Err("Usage: chat-rust --url <ws://host:port/ws>"),
    }
}

fn reset(state: &mut ClientState, protocol: &mut protocol::ProtocolState) {
    state::disconnected(state);
    protocol.login_correlation = None;
    protocol.send_correlation = None;
}

fn current_correlation(protocol: &protocol::ProtocolState) -> Option<uuid::Uuid> {
    protocol.send_correlation.or(protocol.login_correlation)
}

async fn close(connection: transport::Connection, correlation: Option<uuid::Uuid>) {
    if let Err(error) = transport::close(connection).await {
        terminal::diagnostic(&error, correlation);
    }
}

async fn send(state: &mut ClientState, protocol: &mut protocol::ProtocolState, payload: String) {
    let correlation = protocol::correlation(&payload);
    if let Some(connection) = state.connection.as_mut()
        && let Err(error) = transport::send(connection, payload).await
    {
        terminal::error(&format!("WebSocket send failed: {error}"), correlation);
        reset(state, protocol);
        terminal::output("Disconnected");
    }
}

#[tokio::main]
async fn main() {
    let server_url = match url() {
        Ok(url) => url,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(2);
        }
    };
    let mut state = state::initial(server_url);
    let mut protocol = protocol::ProtocolState::default();
    let mut attempt = None;
    let mut input = terminal::input();
    let mut closing = tokio::task::JoinSet::new();
    terminal::output("Chat ready. Use /help for commands.");

    loop {
        let action = tokio::select! {
            line = input.recv() => Action::Input(line),
            connected = transport::finish(&mut attempt) => Action::Connected(connected),
            event = transport::receive(&mut state.connection) => Action::Network(event),
        };
        while let Some(result) = closing.try_join_next() {
            if let Err(error) = result {
                terminal::diagnostic(&format!("Close task failed: {error}"), None);
            }
        }
        match action {
            Action::Input(line) => {
                let command = match line {
                    Some(Ok(line)) => match terminal::parse(&line) {
                        Ok(command) => command,
                        Err(error) => {
                            terminal::error(error, None);
                            continue;
                        }
                    },
                    Some(Err(error)) => {
                        terminal::diagnostic(
                            &format!("stdin read failed: {error}"),
                            current_correlation(&protocol),
                        );
                        Command::Quit
                    }
                    None => Command::Quit,
                };
                match command {
                    Command::Connect(name) => {
                        if state.connection_state != ConnectionState::Disconnected {
                            continue;
                        }
                        let Some(name) = name.or_else(|| state.remembered_username.clone()) else {
                            terminal::diagnostic("Username required: /connect <username>", None);
                            terminal::output("Username required: /connect <username>");
                            continue;
                        };
                        state.login_username = Some(name);
                        state.connection_state = ConnectionState::Connecting;
                        attempt = Some(transport::connect(state.server_url.clone()));
                        terminal::output("Connecting");
                    }
                    Command::Disconnect | Command::DropConnection => {
                        let graceful = matches!(command, Command::Disconnect);
                        if state.connection_state == ConnectionState::Disconnected {
                            continue;
                        }
                        attempt = None;
                        if let Some(connection) = state.connection.take() {
                            if graceful {
                                closing.spawn(close(connection, current_correlation(&protocol)));
                            } else {
                                transport::drop_connection(connection);
                            }
                        }
                        reset(&mut state, &mut protocol);
                        terminal::output("Disconnected");
                    }
                    Command::Send { recipient, text } => {
                        if state.session_state != SessionState::LoggedIn {
                            terminal::error("Login required before /send", None);
                            continue;
                        }
                        if protocol.send_correlation.is_some() {
                            terminal::error(
                                "A send is pending; wait for its response",
                                protocol.send_correlation,
                            );
                            continue;
                        }
                        let (correlation, payload) = protocol::send(&recipient, &text);
                        protocol.send_correlation = Some(correlation);
                        send(&mut state, &mut protocol, payload).await;
                    }
                    Command::Status => terminal::output(&terminal::status(&state)),
                    Command::Help => terminal::output(terminal::HELP),
                    Command::Quit => {
                        if let Some(connection) = state.connection.take() {
                            close(connection, current_correlation(&protocol)).await;
                        }
                        while let Some(result) = closing.join_next().await {
                            if let Err(error) = result {
                                terminal::diagnostic(&format!("Close task failed: {error}"), None);
                            }
                        }
                        break;
                    }
                }
            }
            Action::Connected(result) => {
                attempt = None;
                match result {
                    Ok(connection) => {
                        state.connection = Some(connection);
                        state.connection_state = ConnectionState::Connected;
                        state.session_state = SessionState::LoginPending;
                        let (correlation, payload) =
                            protocol::login(state.login_username.as_deref().unwrap());
                        protocol.login_correlation = Some(correlation);
                        terminal::output("Connected; login pending");
                        send(&mut state, &mut protocol, payload).await;
                    }
                    Err(error) => {
                        terminal::error(
                            &format!("WebSocket connect failed: {error}"),
                            current_correlation(&protocol),
                        );
                        reset(&mut state, &mut protocol);
                        terminal::output("Disconnected");
                    }
                }
            }
            Action::Network(event) => match event {
                Ok(transport::Event::Text(text)) => {
                    let effect = protocol::handle(&mut state, &mut protocol, &text);
                    if let Some((cause, correlation)) = effect.diagnostic {
                        terminal::diagnostic(&cause, correlation);
                    }
                    if let Some(display) = effect.display {
                        terminal::output_for(&display, protocol::correlation(&text));
                    }
                    if let Some(acknowledgment) = effect.acknowledgment {
                        send(&mut state, &mut protocol, acknowledgment).await;
                    }
                }
                Ok(transport::Event::Ping) => {
                    state.last_heartbeat_at = Some(chrono::Utc::now());
                    if let Some(connection) = state.connection.as_mut()
                        && let Err(error) = transport::pong(connection).await
                    {
                        terminal::error(
                            &format!("WebSocket pong failed: {error}"),
                            current_correlation(&protocol),
                        );
                        reset(&mut state, &mut protocol);
                        terminal::output("Disconnected");
                    }
                }
                Ok(transport::Event::Other) => {}
                Ok(transport::Event::Invalid(cause)) => {
                    terminal::diagnostic(cause, current_correlation(&protocol))
                }
                Ok(transport::Event::Closed) => {
                    reset(&mut state, &mut protocol);
                    terminal::output("Disconnected");
                }
                Err(error) => {
                    terminal::diagnostic(
                        &format!("WebSocket receive failed: {error}"),
                        current_correlation(&protocol),
                    );
                    reset(&mut state, &mut protocol);
                    terminal::output("Disconnected");
                }
            },
        }
    }
}
