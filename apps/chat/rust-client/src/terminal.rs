use crate::state::{ClientState, ConnectionState, SessionState};
use linefeed::{Interface, ReadResult, terminal::DefaultTerminal};
use std::{
    io::{self, BufRead, IsTerminal, Write},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread::JoinHandle,
    time::Duration,
};
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

pub fn parse(line: &str) -> Result<Command, String> {
    let line = line.trim_start();
    let (verb, arguments) = line.split_once(char::is_whitespace).unwrap_or((line, ""));
    match verb {
        "/connect" => {
            let mut names = arguments.split_whitespace();
            let name = names.next().map(str::to_owned);
            if names.next().is_some() {
                return Err(format!(
                    "Invalid command {line:?}. Usage: /connect [username]"
                ));
            }
            Ok(Command::Connect(name))
        }
        "/send" => {
            let arguments = arguments.trim_start();
            let (recipient, text) = arguments.split_once(char::is_whitespace).ok_or_else(|| {
                format!("Invalid command {line:?}. Usage: /send <recipient> <text>")
            })?;
            if recipient.is_empty() || text.trim().is_empty() {
                return Err(format!(
                    "Invalid command {line:?}. Usage: /send <recipient> <text>"
                ));
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
        "/login" => Err("Unknown command '/login'. Use /connect <username>.".into()),
        _ => Err(format!("Unknown or invalid command {line:?}. Use /help.")),
    }
}

#[derive(Clone)]
pub struct Display {
    editor: Option<Arc<Interface<DefaultTerminal>>>,
}

pub struct Input {
    receiver: UnboundedReceiver<io::Result<String>>,
    stopped: Arc<AtomicBool>,
    reader: Option<JoinHandle<()>>,
}

pub fn open() -> io::Result<(Display, Input)> {
    // Keep the interactive screen on stderr so failures use the same serialized
    // writer as prompt restoration; piped commands retain separate output streams.
    let editor = if io::stdin().is_terminal() && io::stderr().is_terminal() {
        let editor = Interface::with_term("chat-rust", DefaultTerminal::stderr()?)?;
        editor.set_prompt("> ")?;
        Some(Arc::new(editor))
    } else {
        None
    };
    let (sender, receiver) = unbounded_channel();
    let stopped = Arc::new(AtomicBool::new(false));
    let reader = if let Some(editor) = editor.clone() {
        let stopped = stopped.clone();
        Some(std::thread::spawn(move || {
            while !stopped.load(Ordering::Acquire) {
                match editor.read_line_step(Some(Duration::from_millis(50))) {
                    Ok(Some(ReadResult::Input(line))) => {
                        if sender.send(Ok(line)).is_err() {
                            break;
                        }
                    }
                    Ok(Some(ReadResult::Eof)) => break,
                    Ok(Some(ReadResult::Signal(_))) | Ok(None) => {}
                    Err(error) => {
                        let _ = sender.send(Err(error));
                        break;
                    }
                }
            }
            if let Err(error) = editor.cancel_read_line() {
                write_error(&format!("Terminal cleanup failed: {error}"), None);
            }
        }))
    } else {
        // A blocked pipe read must not prevent /quit from exiting.
        std::thread::spawn(move || {
            for line in io::stdin().lock().lines() {
                let failed = line.is_err();
                if sender.send(line).is_err() || failed {
                    break;
                }
            }
        });
        None
    };
    Ok((
        Display { editor },
        Input {
            receiver,
            stopped,
            reader,
        },
    ))
}

impl Input {
    pub async fn recv(&mut self) -> Option<io::Result<String>> {
        self.receiver.recv().await
    }
}

impl Drop for Input {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::Release);
        if let Some(reader) = self.reader.take()
            && reader.join().is_err()
        {
            write_error("Terminal input thread failed", None);
        }
    }
}

fn error_message(cause: &str, correlation: Option<Uuid>) -> String {
    match correlation {
        Some(id) => format!("✗ Error: {cause}; correlation_id={id}"),
        None => format!("✗ Error: {cause}"),
    }
}

fn write_error(cause: &str, correlation: Option<Uuid>) {
    let mut stderr = io::stderr().lock();
    if writeln!(stderr, "{}\n", error_message(cause, correlation))
        .and_then(|_| stderr.flush())
        .is_err()
    {
        std::process::exit(1);
    }
}

impl Display {
    pub fn output(&self, message: &str) {
        self.output_for(message, None);
    }

    pub fn error(&self, cause: &str, correlation: Option<Uuid>) {
        if let Some(editor) = &self.editor {
            if let Err(error) = editor
                .lock_writer_erase()
                .and_then(|mut writer| writeln!(writer, "{}\n", error_message(cause, correlation)))
            {
                write_error(&format!("Terminal write failed: {error}"), correlation);
            }
        } else {
            write_error(cause, correlation);
        }
    }

    pub fn output_for(&self, message: &str, correlation: Option<Uuid>) {
        let result = if let Some(editor) = &self.editor {
            editor
                .lock_writer_erase()
                .and_then(|mut writer| writeln!(writer, "{message}\n"))
        } else {
            let mut stdout = io::stdout().lock();
            writeln!(stdout, "{message}\n").and_then(|_| stdout.flush())
        };
        if let Err(error) = result {
            self.error(&format!("stdout write failed: {error}"), correlation);
        }
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
