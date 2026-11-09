use chat_rust::{protocol, queue, state, terminal, transport};
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
}

fn current_correlation(
    state: &ClientState,
    protocol: &protocol::ProtocolState,
) -> Option<uuid::Uuid> {
    queue::current_correlation(&state.outgoing_queue).or(protocol.login_correlation)
}

fn flush_messages(
    state: &mut ClientState,
    protocol: &mut protocol::ProtocolState,
    display: &terminal::Display,
) {
    let (Some(user), Some(connection)) =
        (state.authenticated_user.as_ref(), state.connection.as_mut())
    else {
        return;
    };
    if let Err((correlation, cause)) =
        queue::flush_messages(&mut state.outgoing_queue, &user.name, connection)
    {
        display.error(
            &format!("WebSocket send failed: {cause}. Use /connect to reconnect"),
            Some(correlation),
        );
        reset(state, protocol);
        display.output("Disconnected");
    }
}

async fn close(
    connection: transport::Connection,
    correlation: Option<uuid::Uuid>,
    display: terminal::Display,
) {
    if let Err(error) = transport::close(connection).await {
        display.error(&error, correlation);
    }
}

fn send(
    state: &mut ClientState,
    protocol: &mut protocol::ProtocolState,
    payload: String,
    display: &terminal::Display,
) {
    let correlation = protocol::correlation(&payload);
    if let Some(connection) = state.connection.as_mut()
        && let Err(error) = transport::send(connection, payload)
    {
        display.error(
            &format!("WebSocket send failed: {error}. Use /connect to reconnect"),
            correlation,
        );
        reset(state, protocol);
        display.output("Disconnected");
    }
}

#[tokio::main]
async fn main() {
    let server_url = match url() {
        Ok(url) => url,
        Err(error) => {
            eprintln!("✗ Error: {error}");
            std::process::exit(2);
        }
    };
    let mut state = state::initial(server_url);
    let mut protocol = protocol::ProtocolState::default();
    let mut attempt = None;
    let (display, mut input) = match terminal::open() {
        Ok(terminal) => terminal,
        Err(error) => {
            eprintln!("✗ Error: Terminal setup failed: {error}");
            std::process::exit(1);
        }
    };
    let mut closing = tokio::task::JoinSet::new();
    display.output("Chat ready. Use /help for commands.");

    loop {
        let action = tokio::select! {
            line = input.recv() => Action::Input(line),
            connected = transport::finish(&mut attempt) => Action::Connected(connected),
            event = transport::receive(&mut state.connection) => Action::Network(event),
        };
        while let Some(result) = closing.try_join_next() {
            if let Err(error) = result {
                display.error(&format!("Close task failed: {error}"), None);
            }
        }
        match action {
            Action::Input(line) => {
                let command = match line {
                    Some(Ok(line)) => match terminal::parse(&line) {
                        Ok(command) => command,
                        Err(error) => {
                            display.error(&error, None);
                            continue;
                        }
                    },
                    Some(Err(error)) => {
                        display.error(
                            &format!("stdin read failed: {error}"),
                            current_correlation(&state, &protocol),
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
                            display.error("Username required: /connect <username>", None);
                            continue;
                        };
                        state.login_username = Some(name);
                        state.connection_state = ConnectionState::Connecting;
                        attempt = Some(transport::connect(state.server_url.clone()));
                        display.output("Connecting");
                    }
                    Command::Disconnect | Command::DropConnection => {
                        let graceful = matches!(command, Command::Disconnect);
                        if state.connection_state == ConnectionState::Disconnected {
                            continue;
                        }
                        attempt = None;
                        if let Some(connection) = state.connection.take() {
                            if graceful {
                                closing.spawn(close(
                                    connection,
                                    current_correlation(&state, &protocol),
                                    display.clone(),
                                ));
                            } else {
                                transport::drop_connection(connection);
                            }
                        }
                        reset(&mut state, &mut protocol);
                        display.output("Disconnected");
                    }
                    Command::Send { recipient, text } => {
                        let sender = match state.session_state {
                            SessionState::LoggedIn => state
                                .authenticated_user
                                .as_ref()
                                .map(|user| user.name.clone()),
                            _ if state.connection_state == ConnectionState::Disconnected => {
                                state.remembered_username.clone()
                            }
                            _ => None,
                        };
                        let Some(sender) = sender else {
                            display.error(
                                "Cannot use /send while logged out. Use /connect <username> first",
                                None,
                            );
                            continue;
                        };
                        queue::enqueue(&mut state.outgoing_queue, sender, recipient, text);
                        if state.session_state == SessionState::LoggedIn {
                            flush_messages(&mut state, &mut protocol, &display);
                        } else {
                            display.output("✓ Queued locally");
                        }
                    }
                    Command::Status => display.output(&terminal::status(&state)),
                    Command::Help => display.output(terminal::HELP),
                    Command::Quit => {
                        if let Some(connection) = state.connection.take() {
                            close(
                                connection,
                                current_correlation(&state, &protocol),
                                display.clone(),
                            )
                            .await;
                        }
                        while let Some(result) = closing.join_next().await {
                            if let Err(error) = result {
                                display.error(&format!("Close task failed: {error}"), None);
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
                        display.output("Connected; login pending");
                        send(&mut state, &mut protocol, payload, &display);
                    }
                    Err(error) => {
                        display.error(
                            &format!("WebSocket connect failed: {error}"),
                            current_correlation(&state, &protocol),
                        );
                        reset(&mut state, &mut protocol);
                        display.output("Disconnected");
                    }
                }
            }
            Action::Network(event) => match event {
                Ok(transport::Event::Text(text)) => {
                    let effect = protocol::handle(&mut state, &mut protocol, &text);
                    if let Some((cause, correlation)) = effect.diagnostic {
                        display.error(&cause, correlation);
                    }
                    if let Some(message) = effect.display {
                        display.output_for(&message, protocol::correlation(&text));
                    }
                    if let Some(acknowledgment) = effect.acknowledgment {
                        send(&mut state, &mut protocol, acknowledgment, &display);
                    }
                    if effect.logged_in {
                        flush_messages(&mut state, &mut protocol, &display);
                    }
                }
                Ok(transport::Event::Ping) => {
                    state.last_heartbeat_at = Some(chrono::Utc::now());
                    if let Some(connection) = state.connection.as_mut()
                        && let Err(error) = transport::pong(connection)
                    {
                        display.error(
                            &format!("WebSocket pong failed: {error}. Use /connect to reconnect"),
                            current_correlation(&state, &protocol),
                        );
                        reset(&mut state, &mut protocol);
                        display.output("Disconnected");
                    }
                }
                Ok(transport::Event::Other) => {}
                Ok(transport::Event::SendFailed(cause, correlation)) => {
                    display.error(
                        &format!("WebSocket send failed: {cause}. Use /connect to reconnect"),
                        correlation,
                    );
                    reset(&mut state, &mut protocol);
                    display.output("Disconnected");
                }
                Ok(transport::Event::Invalid(cause)) => {
                    display.error(cause, current_correlation(&state, &protocol))
                }
                Ok(transport::Event::Closed) => {
                    display.output("Connection closed by server. Use /connect to reconnect");
                    reset(&mut state, &mut protocol);
                    display.output("Disconnected");
                }
                Err(error) => {
                    display.error(
                        &format!("WebSocket receive failed: {error}. Use /connect to reconnect"),
                        current_correlation(&state, &protocol),
                    );
                    reset(&mut state, &mut protocol);
                    display.output("Disconnected");
                }
            },
        }
    }
}
