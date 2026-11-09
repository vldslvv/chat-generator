use futures_util::{SinkExt, StreamExt};
use std::{future::Future, pin::Pin, time::Duration};
use tokio::net::TcpStream;
use tokio_tungstenite::{
    MaybeTlsStream, WebSocketStream, connect_async,
    tungstenite::{
        Message,
        protocol::{CloseFrame, frame::coding::CloseCode},
    },
};

pub struct Connection(Box<WebSocketStream<MaybeTlsStream<TcpStream>>>);
pub type Attempt = Pin<Box<dyn Future<Output = Result<Connection, String>> + Send>>;

pub enum Event {
    Text(String),
    Ping,
    Other,
    Invalid(&'static str),
    Closed,
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
            .map(|(socket, _)| Connection(Box::new(socket)))
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
    match connection.0.next().await {
        Some(Ok(Message::Text(text))) => Ok(Event::Text(text.to_string())),
        Some(Ok(Message::Ping(_))) => Ok(Event::Ping),
        Some(Ok(Message::Close(frame))) => {
            validate_close(frame)?;
            connection
                .0
                .flush()
                .await
                .map_err(|error| format!("Close response failed: {error}"))?;
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

pub async fn send(connection: &mut Connection, text: String) -> Result<(), String> {
    connection
        .0
        .send(Message::Text(text.into()))
        .await
        .map_err(|error| error.to_string())
}

pub async fn pong(connection: &mut Connection) -> Result<(), String> {
    // Reading queues tungstenite's matching pong; flushing sends it unchanged.
    connection
        .0
        .flush()
        .await
        .map_err(|error| error.to_string())
}

pub async fn close(mut connection: Connection) -> Result<(), String> {
    tokio::time::timeout(Duration::from_secs(2), async {
        connection
            .0
            .close(None)
            .await
            .map_err(|error| error.to_string())?;
        loop {
            let frame = connection
                .0
                .next()
                .await
                .ok_or("Peer ended connection without a close handshake")?
                .map_err(|error| error.to_string())?;
            if let Message::Close(frame) = frame {
                validate_close(frame)?;
                connection
                    .0
                    .flush()
                    .await
                    .map_err(|error| error.to_string())?;
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
