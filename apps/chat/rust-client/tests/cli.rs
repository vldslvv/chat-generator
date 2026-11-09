use chrono::{DateTime, Utc};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::{process::Stdio, time::Duration};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader, Lines},
    net::{TcpListener, TcpStream},
    process::{Child, ChildStderr, ChildStdin, ChildStdout, Command},
    time::timeout,
};
use tokio_tungstenite::{WebSocketStream, accept_async, tungstenite::Message};
use uuid::Uuid;

const WAIT: Duration = Duration::from_secs(5);
type Peer = WebSocketStream<TcpStream>;

struct Cli {
    child: Child,
    input: ChildStdin,
    output: Lines<BufReader<ChildStdout>>,
    errors: Lines<BufReader<ChildStderr>>,
    transcript: String,
}

impl Cli {
    async fn start(url: &str) -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_chat-rust"))
            .args(["--url", url])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        let input = child.stdin.take().unwrap();
        let output = BufReader::new(child.stdout.take().unwrap()).lines();
        let errors = BufReader::new(child.stderr.take().unwrap()).lines();
        let mut cli = Self {
            child,
            input,
            output,
            errors,
            transcript: String::new(),
        };
        cli.until("Chat ready.").await;
        cli
    }

    async fn command(&mut self, command: &str) {
        self.input
            .write_all(format!("{command}\n").as_bytes())
            .await
            .unwrap();
        self.input.flush().await.unwrap();
    }

    async fn until(&mut self, expected: &str) -> String {
        let result = timeout(WAIT, async {
            loop {
                let line = self
                    .output
                    .next_line()
                    .await
                    .unwrap()
                    .expect("CLI output ended");
                self.transcript.push_str(&line);
                self.transcript.push('\n');
                if line.contains(expected) {
                    return line;
                }
            }
        })
        .await;
        result.unwrap_or_else(|_| panic!("Missing {expected:?}; output:\n{}", self.transcript))
    }

    async fn quit(&mut self) {
        self.command("/quit").await;
        assert!(
            timeout(WAIT, self.child.wait())
                .await
                .unwrap()
                .unwrap()
                .success()
        );
    }

    async fn diagnostic(&mut self, cause: &str, correlation: Option<&str>) -> String {
        timeout(WAIT, async {
            loop {
                let line = self
                    .errors
                    .next_line()
                    .await
                    .unwrap()
                    .expect("stderr ended");
                if line.contains(cause) {
                    assert!(
                        line.contains(&format!(
                            "correlation_id={}",
                            correlation.unwrap_or("unavailable")
                        )),
                        "{line}"
                    );
                    return line;
                }
            }
        })
        .await
        .unwrap_or_else(|_| panic!("Missing stderr cause: {cause}"))
    }
}

async fn listener() -> (TcpListener, String) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("ws://{}/ws", listener.local_addr().unwrap());
    (listener, url)
}

async fn accept(listener: &TcpListener) -> Peer {
    let (stream, _) = timeout(WAIT, listener.accept()).await.unwrap().unwrap();
    timeout(WAIT, accept_async(stream)).await.unwrap().unwrap()
}

async fn frame(peer: &mut Peer) -> Message {
    timeout(WAIT, peer.next()).await.unwrap().unwrap().unwrap()
}

async fn request(peer: &mut Peer, action: &str) -> Value {
    let frame = frame(peer).await;
    let Message::Text(text) = frame else {
        panic!("Expected request, received {frame:?}")
    };
    let request: Value = serde_json::from_str(&text).unwrap();
    assert_eq!(request["type"], action);
    Uuid::parse_str(request["correlation_id"].as_str().unwrap()).unwrap();
    assert!(request["data"].is_object());
    request
}

async fn reply(peer: &mut Peer, value: Value) {
    peer.send(Message::Text(value.to_string().into()))
        .await
        .unwrap();
}

async fn login(cli: &mut Cli, listener: &TcpListener, command: &str, name: &str) -> Peer {
    cli.command(command).await;
    let mut peer = accept(listener).await;
    let request = request(&mut peer, "login").await;
    assert_eq!(request["data"], json!({"name": name}));
    reply(
        &mut peer,
        json!({"type":"login_ok", "correlation_id": request["correlation_id"],
        "data":{"id":Uuid::new_v4(), "name":name}}),
    )
    .await;
    cli.until(&format!("Logged in as {name}")).await;
    peer
}

fn message(id: Uuid, text: &str) -> Value {
    json!({"id":id, "sender_id":Uuid::new_v4(), "recipient_id":Uuid::new_v4(),
        "text":text, "client_sent_at":0, "server_received_at":"2026-11-08T12:00:00Z",
        "recipient_received_at":null, "server_ack_received_at":null})
}

#[tokio::test]
async fn local_commands_validate_and_stay_usable_without_connection() {
    let mut cli = Cli::start("ws://127.0.0.1:1/ws").await;
    cli.command("/status").await;
    cli.until("Last heartbeat: never").await;
    assert!(cli.transcript.contains(
        "Server: ws://127.0.0.1:1/ws\nConnection: disconnected\nSession: none\nUser: -\n"
    ));
    cli.command("/connect").await;
    cli.until("Username required: /connect <username>").await;
    cli.diagnostic("Username required", None).await;
    for command in ["/send", "/send bob", "/send bob    "] {
        cli.command(command).await;
        cli.until("Usage: /send <recipient> <text>").await;
        cli.diagnostic("Usage: /send <recipient> <text>", None)
            .await;
    }
    cli.command("/send bob hello").await;
    cli.until("Login required").await;
    cli.diagnostic("Login required", None).await;
    cli.command("/unknown").await;
    cli.until("Unknown command").await;
    cli.diagnostic("Unknown command", None).await;
    cli.command("/disconnect").await;
    cli.command("/drop-connection").await;
    cli.command("/help").await;
    cli.until("/quit").await;
    for syntax in [
        "/connect [username]",
        "/disconnect",
        "/drop-connection",
        "/send <recipient> <text>",
        "/status",
        "/help",
    ] {
        assert!(cli.transcript.contains(syntax));
    }
    cli.quit().await;
}

#[tokio::test]
async fn commands_remain_responsive_during_handshake_and_attempt_can_be_cancelled() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    cli.command("/connect alice").await;
    let (mut stream, _) = timeout(WAIT, listener.accept()).await.unwrap().unwrap();
    let mut bytes = [0; 1024];
    assert!(
        timeout(WAIT, stream.read(&mut bytes))
            .await
            .unwrap()
            .unwrap()
            > 0
    );
    cli.command("/connect mallory").await;
    cli.command("/status").await;
    cli.until("Last heartbeat: never").await;
    assert!(
        cli.transcript
            .contains("Connection: connecting\nSession: none\nUser: -")
    );
    assert!(
        timeout(Duration::from_millis(100), listener.accept())
            .await
            .is_err()
    );
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    assert_eq!(
        timeout(WAIT, stream.read(&mut bytes))
            .await
            .unwrap()
            .unwrap(),
        0
    );
    cli.command("/connect").await;
    cli.until("Username required").await;
    drop(listener);
    cli.command("/connect alice").await;
    cli.until("Disconnected").await;
    let failure = cli.diagnostic("WebSocket connect failed", None).await;
    assert!(failure.contains("Connection refused"));
    cli.command("/status").await;
    cli.until("Last heartbeat: never").await;
    assert!(
        cli.transcript
            .contains("Connection: disconnected\nSession: none\nUser: -")
    );
    cli.quit().await;
}

#[tokio::test]
async fn pending_login_correlation_heartbeat_and_rejection_preserve_local_lifecycle() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    cli.command("/connect bad_name").await;
    let mut peer = accept(&listener).await;
    let login = request(&mut peer, "login").await;
    cli.until("Connected; login pending").await;
    let wrong_correlation = Uuid::new_v4().to_string();
    reply(
        &mut peer,
        json!({"type":"login_ok", "correlation_id":wrong_correlation,
        "data":{"id":Uuid::new_v4(), "name":"wrong"}}),
    )
    .await;
    cli.diagnostic("mismatched correlation ID", Some(&wrong_correlation))
        .await;
    let before = Utc::now();
    peer.send(Message::Ping(b"heartbeat".to_vec().into()))
        .await
        .unwrap();
    assert_eq!(
        frame(&mut peer).await,
        Message::Pong(b"heartbeat".to_vec().into())
    );
    cli.command("/connect another").await;
    cli.command("/send bob blocked").await;
    cli.until("Login required").await;
    cli.command("/status").await;
    let heartbeat = cli.until("Last heartbeat:").await;
    let time =
        DateTime::parse_from_rfc3339(heartbeat.strip_prefix("Last heartbeat: ").unwrap()).unwrap();
    assert!(time >= before && time <= Utc::now());
    assert!(
        cli.transcript
            .contains("Connection: connected\nSession: login pending\nUser: -")
    );
    reply(
        &mut peer,
        json!({"type":"error", "correlation_id":login["correlation_id"],
        "data":{"message":"Name rejected"}}),
    )
    .await;
    cli.until("✗ Error: Name rejected").await;
    cli.diagnostic("Name rejected", login["correlation_id"].as_str())
        .await;
    cli.command("/status").await;
    cli.until("Last heartbeat:").await;
    assert!(
        cli.transcript
            .contains("Connection: connected\nSession: none\nUser: -")
    );
    cli.command("/disconnect").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    peer.flush().await.unwrap();
    cli.until("Disconnected").await;
    cli.command("/connect").await;
    cli.until("Username required").await;
    cli.quit().await;
}

#[tokio::test]
async fn messages_acknowledge_after_display_and_disconnect_remembers_only_successful_login() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    let mut peer = login(&mut cli, &listener, "/connect alice", "alice").await;
    cli.command("/connect bob").await;
    cli.command("/send bob   hello  world  ").await;
    let before = Utc::now();
    let sent = request(&mut peer, "send").await;
    assert_eq!(sent["data"]["recipient"], "bob");
    assert_eq!(sent["data"]["text"], "  hello  world  ");
    let sent_at =
        DateTime::parse_from_rfc3339(sent["data"]["client_sent_at"].as_str().unwrap()).unwrap();
    assert!((Utc::now() - sent_at.with_timezone(&Utc)).num_seconds() < 5);
    let id = Uuid::new_v4();
    let unsolicited = Uuid::new_v4();
    let wrong_correlation = Uuid::new_v4().to_string();
    reply(&mut peer, json!({"type":"message_accepted", "correlation_id":wrong_correlation, "data":message(unsolicited,"wrong reply")})).await;
    cli.diagnostic("mismatched correlation ID", Some(&wrong_correlation))
        .await;
    cli.command("/send bob overlapping").await;
    cli.until("A send is pending").await;
    cli.diagnostic("A send is pending", sent["correlation_id"].as_str())
        .await;
    reply(&mut peer, json!({"type":"message_accepted", "correlation_id":sent["correlation_id"], "data":message(id,"  hello  world  ")})).await;
    cli.until(&format!("✓ Accepted {id}")).await;
    assert!(
        !cli.transcript
            .contains(&format!("✓ Accepted {unsolicited}"))
    );
    cli.command("/send offline rejected").await;
    let rejected = request(&mut peer, "send").await;
    assert_ne!(rejected["correlation_id"], sent["correlation_id"]);
    reply(&mut peer, json!({"type":"error", "correlation_id":rejected["correlation_id"], "data":{"message":"Recipient is offline"}})).await;
    cli.until("✗ Error: Recipient is offline").await;
    cli.diagnostic("Recipient is offline", rejected["correlation_id"].as_str())
        .await;
    cli.command("/send bob after error").await;
    let next = request(&mut peer, "send").await;
    let next_id = Uuid::new_v4();
    reply(&mut peer, json!({"type":"message_accepted", "correlation_id":next["correlation_id"], "data":message(next_id,"after error")})).await;
    cli.until(&format!("✓ Accepted {next_id}")).await;
    let incoming = Uuid::new_v4();
    reply(
        &mut peer,
        json!({"type":"message_received", "data":message(incoming,"incoming  text")}),
    )
    .await;
    let ack = request(&mut peer, "ack").await;
    cli.until(": incoming  text").await;
    assert_eq!(ack["data"]["message_id"], incoming.to_string());
    assert_ne!(ack["correlation_id"], sent["correlation_id"]);
    let received_at =
        DateTime::parse_from_rfc3339(ack["data"]["recipient_received_at"].as_str().unwrap())
            .unwrap();
    assert!(received_at >= before && received_at <= Utc::now());
    peer.send(Message::Ping(b"last".to_vec().into()))
        .await
        .unwrap();
    assert_eq!(
        frame(&mut peer).await,
        Message::Pong(b"last".to_vec().into())
    );
    cli.command("/status").await;
    let heartbeat = cli.until("Last heartbeat:").await;
    assert!(
        cli.transcript
            .contains("Connection: connected\nSession: logged in\nUser: alice")
    );
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    // A Close frame would be a graceful shutdown and violates /drop-connection.
    assert!(
        timeout(WAIT, peer.next())
            .await
            .unwrap()
            .is_none_or(|frame| frame.is_err())
    );
    cli.command("/send bob no queue").await;
    cli.until("Login required").await;
    cli.command("/status").await;
    assert_eq!(cli.until("Last heartbeat:").await, heartbeat);
    assert!(
        cli.transcript
            .contains("Connection: disconnected\nSession: none\nUser: -")
    );
    assert!(
        timeout(Duration::from_millis(100), listener.accept())
            .await
            .is_err()
    );
    let mut peer = login(&mut cli, &listener, "/connect", "alice").await;
    assert!(
        timeout(Duration::from_millis(100), peer.next())
            .await
            .is_err()
    );
    cli.command("/quit").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    peer.flush().await.unwrap();
    assert!(
        timeout(WAIT, cli.child.wait())
            .await
            .unwrap()
            .unwrap()
            .success()
    );
    assert!(!cli.transcript.contains("delivered"));
}

#[tokio::test]
async fn server_connection_loss_resets_authentication_without_reconnecting() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    let mut peer = login(&mut cli, &listener, "/connect alice", "alice").await;
    cli.command("/send bob awaiting response").await;
    let pending = request(&mut peer, "send").await;
    drop(peer);
    cli.until("Disconnected").await;
    let failure = cli
        .diagnostic(
            "WebSocket receive failed",
            pending["correlation_id"].as_str(),
        )
        .await;
    assert!(failure.contains("without closing handshake"));
    cli.command("/status").await;
    cli.until("Last heartbeat: never").await;
    assert!(
        cli.transcript
            .contains("Connection: disconnected\nSession: none\nUser: -")
    );
    assert!(
        timeout(Duration::from_millis(100), listener.accept())
            .await
            .is_err()
    );
    let mut peer = login(&mut cli, &listener, "/connect", "alice").await;
    cli.command("/disconnect").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    peer.flush().await.unwrap();
    cli.until("Disconnected").await;
    cli.quit().await;
}

#[tokio::test]
async fn malformed_server_event_logs_recoverable_correlation_and_keeps_connection_usable() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    cli.command("/connect alice").await;
    let mut peer = accept(&listener).await;
    let login = request(&mut peer, "login").await;
    reply(
        &mut peer,
        json!({"type":"login_ok", "correlation_id":login["correlation_id"],
        "data":{"id":"broken-user-id", "name":"alice"}}),
    )
    .await;
    let diagnostic = cli
        .diagnostic("Invalid server event", login["correlation_id"].as_str())
        .await;
    assert!(diagnostic.contains("UUID") || diagnostic.contains("invalid character"));
    cli.until("✗ Error: Invalid server event").await;
    peer.send(Message::Text("not json".into())).await.unwrap();
    cli.diagnostic("Invalid server event", None).await;
    peer.send(Message::Binary(vec![1, 2, 3].into()))
        .await
        .unwrap();
    cli.diagnostic(
        "Unexpected non-text server event",
        login["correlation_id"].as_str(),
    )
    .await;
    reply(
        &mut peer,
        json!({"type":"login_ok", "correlation_id":login["correlation_id"],
        "data":{"id":Uuid::new_v4(), "name":"alice"}}),
    )
    .await;
    cli.until("Logged in as alice").await;
    cli.command("/disconnect").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    peer.flush().await.unwrap();
    cli.until("Disconnected").await;
    cli.quit().await;
}

#[tokio::test]
async fn close_handshake_timeout_logs_pending_correlation_after_local_disconnect() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    cli.command("/connect alice").await;
    let mut peer = accept(&listener).await;
    let login = request(&mut peer, "login").await;
    cli.command("/disconnect").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    cli.until("Disconnected").await;
    // Hold the peer without flushing its automatically queued close response.
    cli.diagnostic(
        "Close handshake timed out",
        login["correlation_id"].as_str(),
    )
    .await;
    cli.command("/status").await;
    cli.until("Last heartbeat: never").await;
    assert!(
        cli.transcript
            .contains("Connection: disconnected\nSession: none\nUser: -")
    );
    cli.quit().await;
}

#[tokio::test]
async fn stdio_read_and_write_failures_report_the_operating_error() {
    let mut invalid_input = Command::new(env!("CARGO_BIN_EXE_chat-rust"))
        .args(["--url", "ws://127.0.0.1:1/ws"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .unwrap();
    invalid_input
        .stdin
        .take()
        .unwrap()
        .write_all(&[0xff, b'\n'])
        .await
        .unwrap();
    let output = timeout(WAIT, invalid_input.wait_with_output())
        .await
        .unwrap()
        .unwrap();
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(
        stderr.contains("stdin read failed")
            && stderr.contains("UTF-8")
            && stderr.contains("correlation_id=unavailable"),
        "{stderr}"
    );

    let mut broken_output = Command::new(env!("CARGO_BIN_EXE_chat-rust"))
        .args(["--url", "ws://127.0.0.1:1/ws"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .unwrap();
    drop(broken_output.stdout.take());
    broken_output
        .stdin
        .take()
        .unwrap()
        .write_all(b"/status\n/quit\n")
        .await
        .unwrap();
    let output = timeout(WAIT, broken_output.wait_with_output())
        .await
        .unwrap()
        .unwrap();
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(
        stderr.contains("stdout write failed")
            && stderr.contains("Broken pipe")
            && stderr.contains("correlation_id=unavailable"),
        "{stderr}"
    );
}
