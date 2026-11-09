use crate::protocol;
use futures_util::{
    SinkExt, StreamExt,
    stream::{SplitSink, SplitStream},
};
use std::{future::Future, pin::Pin, time::Duration};
use tokio::net::TcpStream;
use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender, unbounded_channel};
use tokio::sync::oneshot;
use tokio_tungstenite::{
    MaybeTlsStream, WebSocketStream, connect_async,
    tungstenite::{
        Message,
        protocol::{CloseFrame, frame::coding::CloseCode},
    },
};

type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;

pub struct Connection {
    reader: SplitStream<Socket>,
    writer: tokio::task::JoinHandle<()>,
    outgoing: UnboundedSender<Outgoing>,
    failures: UnboundedReceiver<(String, Option<uuid::Uuid>)>,
}

enum Outgoing {
    Text(String),
    Send {
        correlation: uuid::Uuid,
        recipient: String,
        text: String,
    },
    Flush(Option<oneshot::Sender<Result<(), String>>>),
    Close,
}

impl Drop for Connection {
    fn drop(&mut self) {
        self.writer.abort();
    }
}

async fn write_requests(
    mut writer: SplitSink<Socket, Message>,
    mut outgoing: UnboundedReceiver<Outgoing>,
    failures: UnboundedSender<(String, Option<uuid::Uuid>)>,
) {
    while let Some(request) = outgoing.recv().await {
        let closing = matches!(request, Outgoing::Close);
        let mut completion = None;
        let (payload, correlation) = match request {
            Outgoing::Text(text) => {
                let correlation = protocol::correlation(&text);
                (Some(text), correlation)
            }
            Outgoing::Send {
                correlation,
                recipient,
                text,
            } => (
                Some(protocol::send(correlation, &recipient, &text)),
                Some(correlation),
            ),
            Outgoing::Flush(waiter) => {
                completion = waiter;
                (None, None)
            }
            Outgoing::Close => (None, None),
        };
        let result = match payload {
            Some(text) => writer.send(Message::Text(text.into())).await,
            None if closing => writer.close().await,
            None => writer.flush().await,
        }
        .map_err(|error| error.to_string());
        if let Some(completion) = completion {
            let _ = completion.send(result.clone());
        }
        if let Err(error) = result {
            let _ = failures.send((error, correlation));
            break;
        }
    }
}

fn connected(socket: Socket) -> Connection {
    let (writer, reader) = socket.split();
    let (outgoing, requests) = unbounded_channel();
    let (report, failures) = unbounded_channel();
    Connection {
        reader,
        writer: tokio::spawn(write_requests(writer, requests, report)),
        outgoing,
        failures,
    }
}
pub type Attempt = Pin<Box<dyn Future<Output = Result<Connection, String>> + Send>>;

pub enum Event {
    Text(String),
    Ping,
    Other,
    Invalid(&'static str),
    Closed,
    SendFailed(String, Option<uuid::Uuid>),
}

fn validate_close(frame: Option<CloseFrame>) -> Result<(), String> {
    if let Some(frame) = frame
        && !matches!(frame.code, CloseCode::Normal | CloseCode::Away)
    {
        return Err(format!(
            "Server closed connection: {} {}",
            frame.code, frame.reason
        ));
    }
    Ok(())
}

pub fn connect(url: String) -> Attempt {
    Box::pin(async move {
        connect_async(url)
            .await
            .map(|(socket, _)| connected(socket))
            .map_err(|error| error.to_string())
    })
}

pub async fn finish(attempt: &mut Option<Attempt>) -> Result<Connection, String> {
    match attempt {
        Some(attempt) => attempt.await,
        None => std::future::pending().await,
    }
}

pub async fn receive(connection: &mut Option<Connection>) -> Result<Event, String> {
    let Some(connection) = connection else {
        return std::future::pending().await;
    };
    let frame = tokio::select! {
        frame = connection.reader.next() => frame,
        Some((cause, correlation)) = connection.failures.recv() => {
            return Ok(Event::SendFailed(cause, correlation));
        }
    };
    match frame {
        Some(Ok(Message::Text(text))) => Ok(Event::Text(text.to_string())),
        Some(Ok(Message::Ping(_))) => Ok(Event::Ping),
        Some(Ok(Message::Close(frame))) => {
            validate_close(frame)?;
            let (completed, waiting) = oneshot::channel();
            connection
                .outgoing
                .send(Outgoing::Flush(Some(completed)))
                .map_err(|_| "Close response failed: writer stopped".to_owned())?;
            tokio::time::timeout(Duration::from_secs(2), waiting)
                .await
                .map_err(|_| "Close response timed out".to_owned())?
                .map_err(|_| "Close response failed: writer stopped".to_owned())??;
            Ok(Event::Closed)
        }
        None => Err("WebSocket stream ended without a close handshake".into()),
        Some(Ok(Message::Binary(_))) | Some(Ok(Message::Frame(_))) => {
            Ok(Event::Invalid("Unexpected non-text server event"))
        }
        Some(Ok(_)) => Ok(Event::Other),
        Some(Err(error)) => Err(error.to_string()),
    }
}

pub fn send(connection: &mut Connection, text: String) -> Result<(), String> {
    connection
        .outgoing
        .send(Outgoing::Text(text))
        .map_err(|_| "WebSocket writer stopped".to_owned())
}

pub fn send_message(
    connection: &mut Connection,
    correlation: uuid::Uuid,
    recipient: String,
    text: String,
) -> Result<(), String> {
    connection
        .outgoing
        .send(Outgoing::Send {
            correlation,
            recipient,
            text,
        })
        .map_err(|_| "WebSocket writer stopped".to_owned())
}

pub fn pong(connection: &mut Connection) -> Result<(), String> {
    // Reading queues tungstenite's matching pong; flushing sends it unchanged.
    connection
        .outgoing
        .send(Outgoing::Flush(None))
        .map_err(|_| "WebSocket writer stopped".to_owned())
}

pub async fn close(mut connection: Connection) -> Result<(), String> {
    tokio::time::timeout(Duration::from_secs(2), async {
        connection
            .outgoing
            .send(Outgoing::Close)
            .map_err(|_| "WebSocket writer stopped".to_owned())?;
        loop {
            let frame = connection
                .reader
                .next()
                .await
                .ok_or("Peer ended connection without a close handshake")?
                .map_err(|error| error.to_string())?;
            if let Message::Close(frame) = frame {
                validate_close(frame)?;
                break;
            }
        }
        Ok::<_, String>(())
    })
    .await
    .map_err(|_| "Close handshake timed out".to_owned())?
    .map_err(|error| format!("Close handshake failed: {error}"))
}

pub fn drop_connection(connection: Connection) {
    // Dropping the stream terminates TCP without sending a WebSocket close frame.
    drop(connection);
}
