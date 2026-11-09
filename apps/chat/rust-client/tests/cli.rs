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
        while let Some(line) = timeout(WAIT, self.errors.next_line())
            .await
            .unwrap()
            .unwrap()
        {
            assert!(line.is_empty(), "Unexpected extra stderr output: {line}");
        }
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
                if line.is_empty() {
                    continue;
                }
                assert!(
                    line.starts_with("✗ Error: ") && line.contains(cause),
                    "{line}"
                );
                if let Some(correlation) = correlation {
                    assert!(
                        line.contains(&format!("correlation_id={correlation}")),
                        "{line}"
                    );
                } else {
                    assert!(!line.contains("correlation_id="), "{line}");
                }
                return line;
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
async fn offline_queue_retains_attempts_in_order_and_isolates_sending_users() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    let mut peer = login(&mut cli, &listener, "/connect alice", "alice").await;
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    drop(peer);
    for command in ["/send bob   first  text ", "/send carol second"] {
        cli.command(command).await;
        cli.until("✓ Queued locally").await;
    }
    let before = Utc::now();
    peer = login(&mut cli, &listener, "/connect", "alice").await;
    let first = request(&mut peer, "send").await;
    let second = request(&mut peer, "send").await;
    assert_eq!(first["data"]["recipient"], "bob");
    assert_eq!(first["data"]["text"], "  first  text ");
    assert_eq!(second["data"]["recipient"], "carol");
    assert_eq!(second["data"]["text"], "second");
    assert_ne!(first["correlation_id"], second["correlation_id"]);
    for sent in [&first, &second] {
        let sent_at =
            DateTime::parse_from_rfc3339(sent["data"]["client_sent_at"].as_str().unwrap()).unwrap();
        assert!(sent_at >= before && sent_at <= Utc::now());
    }
    let unknown = Uuid::new_v4().to_string();
    reply(
        &mut peer,
        json!({"type":"message_accepted", "correlation_id":unknown,
        "data":message(Uuid::new_v4(),"unknown")}),
    )
    .await;
    cli.diagnostic("mismatched correlation ID", Some(&unknown))
        .await;
    reply(
        &mut peer,
        json!({"type":"error", "correlation_id":first["correlation_id"],
        "data":{"message":"Recipient does not exist"}}),
    )
    .await;
    cli.diagnostic("Recipient does not exist", first["correlation_id"].as_str())
        .await;
    let accepted = Uuid::new_v4();
    reply(
        &mut peer,
        json!({"type":"message_accepted", "correlation_id":second["correlation_id"],
        "data":message(accepted,"second")}),
    )
    .await;
    cli.until(&format!("✓ Accepted {accepted}")).await;
    cli.command("/send bob third").await;
    let third = request(&mut peer, "send").await;
    assert_eq!(third["data"]["text"], "third");
    assert!(
        timeout(Duration::from_millis(100), peer.next())
            .await
            .is_err()
    );
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    drop(peer);
    cli.command("/send bob fourth").await;
    cli.until("✓ Queued locally").await;

    peer = login(&mut cli, &listener, "/connect bob", "bob").await;
    assert!(
        timeout(Duration::from_millis(100), peer.next())
            .await
            .is_err()
    );
    cli.command("/send alice bob pending").await;
    let bob_attempt = request(&mut peer, "send").await;
    assert_eq!(bob_attempt["data"]["text"], "bob pending");
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    drop(peer);

    peer = login(&mut cli, &listener, "/connect alice", "alice").await;
    let retried = request(&mut peer, "send").await;
    assert_eq!(retried["data"]["text"], "  first  text ");
    assert_ne!(retried["correlation_id"], first["correlation_id"]);
    let retried_third = request(&mut peer, "send").await;
    assert_eq!(retried_third["data"]["text"], "third");
    assert_ne!(retried_third["correlation_id"], third["correlation_id"]);
    assert_eq!(request(&mut peer, "send").await["data"]["text"], "fourth");
    assert!(
        timeout(Duration::from_millis(100), peer.next())
            .await
            .is_err()
    );
    reply(
        &mut peer,
        json!({"type":"message_accepted", "correlation_id":first["correlation_id"],
        "data":message(Uuid::new_v4(),"stale")}),
    )
    .await;
    cli.diagnostic(
        "mismatched correlation ID",
        first["correlation_id"].as_str(),
    )
    .await;
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    drop(peer);

    peer = login(&mut cli, &listener, "/connect", "alice").await;
    for text in ["  first  text ", "third", "fourth"] {
        let sent = request(&mut peer, "send").await;
        assert_eq!(sent["data"]["text"], text);
        let id = Uuid::new_v4();
        reply(
            &mut peer,
            json!({"type":"message_accepted", "correlation_id":sent["correlation_id"],
            "data":message(id,text)}),
        )
        .await;
        cli.until(&format!("✓ Accepted {id}")).await;
    }
    cli.command("/disconnect").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    peer.flush().await.unwrap();
    cli.until("Disconnected").await;
    peer = login(&mut cli, &listener, "/connect bob", "bob").await;
    let bob_retry = request(&mut peer, "send").await;
    assert_eq!(bob_retry["data"]["text"], "bob pending");
    assert_ne!(bob_retry["correlation_id"], bob_attempt["correlation_id"]);
    cli.command("/disconnect").await;
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    peer.flush().await.unwrap();
    cli.until("Disconnected").await;
    cli.quit().await;
}

#[tokio::test]
async fn reconnect_flush_keeps_incoming_events_and_commands_responsive_under_backpressure() {
    let (listener, url) = listener().await;
    let mut cli = Cli::start(&url).await;
    let peer = login(&mut cli, &listener, "/connect alice", "alice").await;
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    drop(peer);
    let command = format!("/send bob {}", "x".repeat(32768));
    for _ in 0..512 {
        cli.command(&command).await;
        cli.until("✓ Queued locally").await;
    }
    let mut peer = login(&mut cli, &listener, "/connect", "alice").await;
    let _ = request(&mut peer, "send").await;
    peer.send(Message::Ping(b"during flush".to_vec().into()))
        .await
        .unwrap();
    let mut incoming = message(Uuid::new_v4(), "event during flush");
    incoming["sender_name"] = json!("bob");
    reply(
        &mut peer,
        json!({"type":"message_received", "data":incoming}),
    )
    .await;
    // Keep the peer's receive side stalled while checking both independent inputs.
    cli.until("← bob: event during flush").await;
    cli.command("/status").await;
    assert_ne!(cli.until("Last heartbeat:").await, "Last heartbeat: never");
    assert!(cli.transcript.contains("Session: logged in\nUser: alice"));
    cli.command("/drop-connection").await;
    cli.until("Disconnected").await;
    cli.quit().await;
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
    assert_eq!(
        cli.diagnostic("Username required", None).await,
        "✗ Error: Username required: /connect <username>"
    );
    for command in ["/send", "/send bob", "/send bob    "] {
        cli.command(command).await;
        let failure = cli
            .diagnostic("Usage: /send <recipient> <text>", None)
            .await;
        assert!(failure.contains(command), "{failure}");
    }
    cli.command("/send bob hello").await;
    cli.diagnostic("Cannot use /send while logged out", None)
        .await;
    cli.command("/unknown").await;
    let failure = cli.diagnostic("Unknown or invalid command", None).await;
    assert!(failure.contains("/unknown") && failure.contains("/help"));
    cli.command("/login bob").await;
    let hint = cli.diagnostic("Unknown command '/login'", None).await;
    assert!(hint.contains("Use /connect <username>"));
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
    assert!(
        !cli.transcript.contains("✗ Error:")
            && !cli.transcript.lines().any(|line| line.starts_with("> "))
    );
    assert!(cli.transcript.contains("Last heartbeat: never\n\n"));
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
    cli.diagnostic("Username required", None).await;
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
    cli.diagnostic("Cannot use /send while logged out", None)
        .await;
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
    cli.diagnostic("Username required", None).await;
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
    let overlapping = request(&mut peer, "send").await;
    assert_eq!(overlapping["data"]["text"], "overlapping");
    let overlapping_id = Uuid::new_v4();
    reply(
        &mut peer,
        json!({"type":"message_accepted", "correlation_id":overlapping["correlation_id"],
        "data":message(overlapping_id,"overlapping")}),
    )
    .await;
    cli.until(&format!("✓ Accepted {overlapping_id}")).await;
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
        json!({"type":"message_received", "data":{
            "sender_name":"bob", "id":incoming,
            "sender_id":Uuid::new_v4(), "recipient_id":Uuid::new_v4(),
            "text":"  incoming  text  ", "client_sent_at":0,
            "server_received_at":"2026-11-08T12:00:00Z",
            "recipient_received_at":null, "server_ack_received_at":null}}),
    )
    .await;
    let ack = request(&mut peer, "ack").await;
    assert_eq!(cli.until("← bob:").await, "← bob:   incoming  text  ");
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
    let retry = request(&mut peer, "send").await;
    assert_eq!(retry["data"]["text"], "rejected");
    assert_ne!(retry["correlation_id"], rejected["correlation_id"]);
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
    assert!(failure.contains("Use /connect to reconnect"));
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
    let retry = request(&mut peer, "send").await;
    assert_eq!(retry["data"]["text"], "awaiting response");
    assert_ne!(retry["correlation_id"], pending["correlation_id"]);
    peer.close(None).await.unwrap();
    assert!(matches!(frame(&mut peer).await, Message::Close(_)));
    cli.until("Connection closed by server. Use /connect to reconnect")
        .await;
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
            && stderr.starts_with("✗ Error: "),
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
            && stderr.starts_with("✗ Error: "),
        "{stderr}"
    );
}

#[cfg(unix)]
struct PtyCli {
    child: Box<dyn portable_pty::Child + Send + Sync>,
    master: Box<dyn portable_pty::MasterPty + Send>,
    initial_local_flags: u64,
    input: Box<dyn std::io::Write + Send>,
    output: tokio::sync::mpsc::UnboundedReceiver<Vec<u8>>,
    screen: vt100::Parser,
}

#[cfg(unix)]
impl PtyCli {
    fn start(url: &str) -> Self {
        let pair = portable_pty::native_pty_system()
            .openpty(portable_pty::PtySize {
                rows: 48,
                cols: 100,
                pixel_width: 0,
                pixel_height: 0,
            })
            .unwrap();
        let initial_local_flags = pair.master.get_termios().unwrap().local_flags.bits() as u64;
        let mut command = portable_pty::CommandBuilder::new(env!("CARGO_BIN_EXE_chat-rust"));
        command.args(["--url", url]);
        command.env("TERM", "xterm-256color");
        let child = pair.slave.spawn_command(command).unwrap();
        drop(pair.slave);
        let mut reader = pair.master.try_clone_reader().unwrap();
        let input = pair.master.take_writer().unwrap();
        let (sender, output) = tokio::sync::mpsc::unbounded_channel();
        std::thread::spawn(move || {
            let mut bytes = [0; 4096];
            while let Ok(length) = reader.read(&mut bytes) {
                if length == 0 || sender.send(bytes[..length].to_vec()).is_err() {
                    break;
                }
            }
        });
        Self {
            child,
            master: pair.master,
            initial_local_flags,
            input,
            output,
            screen: vt100::Parser::new(48.try_into().unwrap(), 100.try_into().unwrap(), 0),
        }
    }

    fn type_text(&mut self, text: &str) {
        self.input.write_all(text.as_bytes()).unwrap();
        self.input.flush().unwrap();
    }

    async fn until(&mut self, expected: &str) {
        timeout(WAIT, async {
            while !self.screen.screen().contents().contains(expected) {
                let bytes = self.output.recv().await.expect("PTY output ended");
                self.screen.process(&bytes);
            }
        })
        .await
        .unwrap_or_else(|_| {
            panic!(
                "Missing {expected:?}; screen:\n{}",
                self.screen.screen().contents()
            )
        });
    }
}

#[cfg(unix)]
impl Drop for PtyCli {
    fn drop(&mut self) {
        if self.child.try_wait().unwrap().is_none() {
            self.child.kill().unwrap();
            self.child.wait().unwrap();
        }
    }
}

#[cfg(unix)]
#[tokio::test]
async fn real_terminal_preserves_unicode_input_cursor_and_completed_blocks_during_events() {
    let (listener, url) = listener().await;
    let mut cli = PtyCli::start(&url);
    cli.until("Chat ready. Use /help for commands.\n\n>").await;
    cli.type_text("/connect alice\r");
    let mut peer = accept(&listener).await;
    let login = request(&mut peer, "login").await;
    reply(
        &mut peer,
        json!({"type":"login_ok", "correlation_id":login["correlation_id"],
        "data":{"id":Uuid::new_v4(), "name":"alice"}}),
    )
    .await;
    cli.until("✓ Logged in as alice\n\n>").await;

    cli.type_text("/send alice héllo界TAIL\x1b[D\x1b[D\x1b[D\x1b[D");
    cli.until("> /send alice héllo界TAIL").await;
    let cursor_column = "> /send alice héllo界".chars().count() as u16 + 1;
    timeout(WAIT, async {
        while cli.screen.screen().cursor_position().1 != cursor_column {
            cli.screen.process(&cli.output.recv().await.unwrap());
        }
    })
    .await
    .unwrap();
    let cursor_row = cli.screen.screen().cursor_position().0;
    let completed = cli
        .screen
        .screen()
        .contents()
        .lines()
        .take(cursor_row.into())
        .collect::<Vec<_>>()
        .join("\n");
    let id = Uuid::new_v4();
    let mut received = message(id, " bonjour  世界 ");
    received["sender_name"] = json!("bob");
    reply(
        &mut peer,
        json!({"type":"message_received", "data":received}),
    )
    .await;
    let _ = request(&mut peer, "ack").await;
    cli.until("← bob:  bonjour  世界 \n\n> /send alice héllo界TAIL")
        .await;
    assert_eq!(
        cli.screen.screen().cursor_position(),
        (cursor_row + 2, cursor_column)
    );
    assert!(cli.screen.screen().contents().starts_with(&completed));
    cli.type_text("X\r");
    let sent = request(&mut peer, "send").await;
    assert_eq!(sent["data"]["text"], "héllo界XTAIL");

    // Self delivery can precede acceptance and must preserve the active editor.
    let mut own = message(Uuid::new_v4(), "héllo界XTAIL");
    own["sender_name"] = json!("alice");
    reply(&mut peer, json!({"type":"message_received", "data":own})).await;
    let _ = request(&mut peer, "ack").await;
    cli.until("← alice: héllo界XTAIL\n\n>").await;
    reply(
        &mut peer,
        json!({"type":"message_accepted", "correlation_id":sent["correlation_id"],
        "data":message(Uuid::new_v4(), "héllo界XTAIL")}),
    )
    .await;
    cli.until("✓ Accepted").await;
    while let Ok(bytes) = cli.output.try_recv() {
        cli.screen.process(&bytes);
    }
    peer.send(Message::Ping(b"silent".to_vec().into()))
        .await
        .unwrap();
    assert_eq!(
        frame(&mut peer).await,
        Message::Pong(b"silent".to_vec().into())
    );
    assert!(
        timeout(Duration::from_millis(100), cli.output.recv())
            .await
            .is_err()
    );

    cli.type_text("/status\r");
    cli.until("Connection: connected\nSession: logged in\nUser: alice\nLast heartbeat:")
        .await;
    cli.type_text("/login alice\r");
    cli.until("✗ Error: Unknown command '/login'. Use /connect <username>.\n\n>")
        .await;
    let screen = cli.screen.screen().contents();
    assert_eq!(screen.matches("✗ Error: Unknown command").count(), 1);
    assert!(screen.contains("Last heartbeat:") && !screen.contains("Last heartbeat: never"));
    drop(peer);
    cli.until("Use /connect to reconnect").await;
    cli.type_text("/status\r");
    cli.until("Connection: disconnected\nSession: none\nUser: -\nLast heartbeat:")
        .await;
    println!(
        "PTY screen after events, cursor restoration, heartbeat, and loss:\n{}",
        cli.screen.screen().contents()
    );
    cli.type_text("/quit\r");
    timeout(WAIT, async {
        loop {
            if let Some(status) = cli.child.try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    let restored = cli.master.get_termios().unwrap();
    assert_eq!(restored.local_flags.bits() as u64, cli.initial_local_flags);
}
