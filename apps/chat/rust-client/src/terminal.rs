use crate::state::{ClientState, ConnectionState, SessionState};
use std::io::{self, BufRead, Write};
use tokio::sync::mpsc::{UnboundedReceiver, unbounded_channel};
use uuid::Uuid;

pub const HELP: &str = "/connect [username]\n/disconnect\n/drop-connection\n/send <recipient> <text>\n/status\n/help\n/quit";

pub enum Command {
    Connect(Option<String>),
    Disconnect,
    DropConnection,
    Send { recipient: String, text: String },
    Status,
    Help,
    Quit,
}

pub fn parse(line: &str) -> Result<Command, &'static str> {
    let line = line.trim_start();
    let (verb, arguments) = line.split_once(char::is_whitespace).unwrap_or((line, ""));
    match verb {
        "/connect" => {
            let mut names = arguments.split_whitespace();
            let name = names.next().map(str::to_owned);
            if names.next().is_some() {
                return Err("Usage: /connect [username]");
            }
            Ok(Command::Connect(name))
        }
        "/send" => {
            let arguments = arguments.trim_start();
            let (recipient, text) = arguments
                .split_once(char::is_whitespace)
                .ok_or("Usage: /send <recipient> <text>")?;
            if recipient.is_empty() || text.trim().is_empty() {
                return Err("Usage: /send <recipient> <text>");
            }
            Ok(Command::Send {
                recipient: recipient.to_owned(),
                text: text.to_owned(),
            })
        }
        "/disconnect" if arguments.trim().is_empty() => Ok(Command::Disconnect),
        "/drop-connection" if arguments.trim().is_empty() => Ok(Command::DropConnection),
        "/status" if arguments.trim().is_empty() => Ok(Command::Status),
        "/help" if arguments.trim().is_empty() => Ok(Command::Help),
        "/quit" if arguments.trim().is_empty() => Ok(Command::Quit),
        _ => Err("Unknown command. Use /help"),
    }
}

pub fn input() -> UnboundedReceiver<io::Result<String>> {
    let (sender, receiver) = unbounded_channel();
    // A dedicated reader lets /quit exit without waiting for another stdin read.
    std::thread::spawn(move || {
        for line in io::stdin().lock().lines() {
            let failed = line.is_err();
            if sender.send(line).is_err() {
                break;
            }
            if failed {
                break;
            }
        }
    });
    receiver
}

pub fn output(message: &str) {
    output_for(message, None);
}

pub fn diagnostic(cause: &str, correlation: Option<Uuid>) {
    let correlation = correlation.map_or_else(|| "unavailable".into(), |id| id.to_string());
    let mut stderr = io::stderr().lock();
    if writeln!(stderr, "Error: {cause}; correlation_id={correlation}").is_err() {
        std::process::exit(1);
    }
}

pub fn error(cause: &str, correlation: Option<Uuid>) {
    diagnostic(cause, correlation);
    output_for(&format!("✗ Error: {cause}"), correlation);
}

pub fn output_for(message: &str, correlation: Option<Uuid>) {
    let mut stdout = io::stdout().lock();
    if let Err(error) = writeln!(stdout, "{message}").and_then(|_| stdout.flush()) {
        diagnostic(&format!("stdout write failed: {error}"), correlation);
    }
}

pub fn status(state: &ClientState) -> String {
    let connection = match state.connection_state {
        ConnectionState::Disconnected => "disconnected",
        ConnectionState::Connecting => "connecting",
        ConnectionState::Connected => "connected",
    };
    let session = match state.session_state {
        SessionState::None => "none",
        SessionState::LoginPending => "login pending",
        SessionState::LoggedIn => "logged in",
    };
    let user = state.authenticated_user.as_ref().map_or("-", |u| &u.name);
    let heartbeat = state
        .last_heartbeat_at
        .map_or_else(|| "never".into(), |time| time.to_rfc3339());
    format!(
        "Server: {}\nConnection: {connection}\nSession: {session}\nUser: {user}\nLast heartbeat: {heartbeat}",
        state.server_url
    )
}
