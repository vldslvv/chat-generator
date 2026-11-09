use crate::state::{self, ClientState, SessionState};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use uuid::Uuid;

#[derive(Deserialize)]
pub struct User {
    pub id: Uuid,
    pub name: String,
}

#[derive(Deserialize)]
#[serde(untagged)]
pub enum ClientTimestamp {
    Timestamp(DateTime<Utc>),
    Zero(Zero),
}

#[derive(Deserialize)]
#[serde(try_from = "u8")]
pub struct Zero;

impl TryFrom<u8> for Zero {
    type Error = &'static str;
    fn try_from(value: u8) -> Result<Self, Self::Error> {
        if value == 0 {
            Ok(Self)
        } else {
            Err("expected zero")
        }
    }
}

#[derive(Deserialize)]
pub struct StoredMessage {
    pub id: Uuid,
    pub sender_id: Uuid,
    pub recipient_id: Uuid,
    pub text: String,
    pub client_sent_at: ClientTimestamp,
    pub server_received_at: DateTime<Utc>,
    pub recipient_received_at: Option<ClientTimestamp>,
    pub server_ack_received_at: Option<DateTime<Utc>>,
}

#[derive(Deserialize)]
pub struct IncomingMessage {
    #[serde(flatten)]
    pub message: StoredMessage,
    pub sender_name: String,
}

#[derive(Deserialize)]
#[serde(tag = "type", content = "data", rename_all = "snake_case")]
pub enum ServerEvent {
    LoginOk(User),
    MessageAccepted(StoredMessage),
    MessageReceived(IncomingMessage),
    Error { message: String },
}

#[derive(Deserialize)]
pub struct Envelope {
    pub correlation_id: Option<Uuid>,
    #[serde(flatten)]
    pub event: ServerEvent,
}

#[derive(Serialize)]
struct Request<'a> {
    #[serde(rename = "type")]
    action: &'a str,
    correlation_id: Uuid,
    data: Value,
}

#[derive(Default)]
pub struct ProtocolState {
    pub login_correlation: Option<Uuid>,
    pub send_correlation: Option<Uuid>,
}

fn request(action: &str, data: Value) -> (Uuid, String) {
    let correlation = Uuid::new_v4();
    let payload = Request {
        action,
        correlation_id: correlation,
        data,
    };
    (correlation, serde_json::to_string(&payload).unwrap())
}

pub fn login(name: &str) -> (Uuid, String) {
    request("login", json!({"name": name}))
}

pub fn send(recipient: &str, text: &str) -> (Uuid, String) {
    request(
        "send",
        json!({"recipient": recipient, "text": text, "client_sent_at": Utc::now()}),
    )
}

pub fn acknowledge(id: Uuid, received_at: DateTime<Utc>) -> String {
    request(
        "ack",
        json!({"message_id": id, "recipient_received_at": received_at}),
    )
    .1
}

pub fn decode(text: &str) -> Result<(Envelope, DateTime<Utc>), serde_json::Error> {
    let envelope = serde_json::from_str(text)?;
    Ok((envelope, Utc::now()))
}

pub struct Effect {
    pub display: Option<String>,
    pub acknowledgment: Option<String>,
    pub diagnostic: Option<(String, Option<Uuid>)>,
}

pub fn correlation(text: &str) -> Option<Uuid> {
    let value: Value = serde_json::from_str(text).ok()?;
    Uuid::parse_str(value.get("correlation_id")?.as_str()?).ok()
}

pub fn handle(state: &mut ClientState, protocol: &mut ProtocolState, text: &str) -> Effect {
    let mut effect = Effect {
        display: None,
        acknowledgment: None,
        diagnostic: None,
    };
    let (envelope, received_at) = match decode(text) {
        Ok(decoded) => decoded,
        Err(error) => {
            effect.diagnostic = Some((format!("Invalid server event: {error}"), correlation(text)));
            return effect;
        }
    };
    let matches_login = protocol.login_correlation.is_some()
        && envelope.correlation_id == protocol.login_correlation;
    match envelope.event {
        ServerEvent::LoginOk(user)
            if matches_login && state.session_state == SessionState::LoginPending =>
        {
            effect.display = Some(format!("✓ Logged in as {}", user.name));
            state::logged_in(state, user);
            protocol.login_correlation = None;
        }
        ServerEvent::MessageAccepted(message)
            if protocol.send_correlation.is_some()
                && envelope.correlation_id == protocol.send_correlation
                && state.session_state == SessionState::LoggedIn =>
        {
            effect.display = Some(format!("✓ Accepted {}", message.id));
            protocol.send_correlation = None;
        }
        ServerEvent::MessageReceived(message)
            if envelope.correlation_id.is_none()
                && state.session_state == SessionState::LoggedIn =>
        {
            effect.display = Some(format!(
                "← {}: {}",
                message.sender_name, message.message.text
            ));
            effect.acknowledgment = Some(acknowledge(message.message.id, received_at));
        }
        ServerEvent::Error { message } => {
            effect.diagnostic = Some((message, envelope.correlation_id));
            if envelope.correlation_id.is_some()
                && envelope.correlation_id == protocol.send_correlation
            {
                protocol.send_correlation = None;
            }
            if matches_login {
                protocol.login_correlation = None;
                state.login_username = None;
                state.session_state = SessionState::None;
            }
        }
        _ => {
            effect.diagnostic = Some((
                "Unexpected server event or mismatched correlation ID".into(),
                envelope.correlation_id,
            ));
        }
    }
    effect
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn message_wire_types_retain_zero_timestamp_and_null_alternatives() {
        let timestamp = "2026-11-08T12:01:02Z";
        let id = "6ab59054-8e3c-4b20-9a11-32922d384f68";
        for (client_time, recipient_time) in [
            (json!(0), Value::Null),
            (json!(timestamp), json!(0)),
            (json!(timestamp), json!(timestamp)),
        ] {
            let wire = json!({
                "type": "message_received",
                "data": {
                    "id": id,
                    "sender_id": "53dd2b06-e8b7-4a19-9c61-9f8df9bf8524",
                    "recipient_id": "629a6d45-679d-4e09-8b3a-d6d779ab415c",
                    "text": "exact  text ",
                    "sender_name": "alice",
                    "client_sent_at": client_time,
                    "server_received_at": timestamp,
                    "recipient_received_at": recipient_time,
                    "server_ack_received_at": null
                }
            });
            let (envelope, _) = decode(&wire.to_string()).unwrap();
            assert!(envelope.correlation_id.is_none());
            let ServerEvent::MessageReceived(message) = envelope.event else {
                panic!("Expected incoming message");
            };
            assert_eq!(message.sender_name, "alice");
            let message = message.message;
            assert_eq!(message.id.to_string(), id);
            assert_eq!(message.text, "exact  text ");
            assert!(message.server_ack_received_at.is_none());
            match (client_time, message.client_sent_at) {
                (Value::Number(number), ClientTimestamp::Zero(_)) => {
                    assert_eq!(number.as_u64(), Some(0))
                }
                (Value::String(_), ClientTimestamp::Timestamp(time)) => {
                    assert_eq!(time.timestamp(), 1794139262);
                }
                _ => panic!("Client timestamp alternative changed"),
            }
            match (recipient_time, message.recipient_received_at) {
                (Value::Null, None) => {}
                (Value::Number(number), Some(ClientTimestamp::Zero(_))) => {
                    assert_eq!(number.as_u64(), Some(0))
                }
                (Value::String(_), Some(ClientTimestamp::Timestamp(time))) => {
                    assert_eq!(time.timestamp(), 1794139262);
                }
                _ => panic!("Recipient timestamp alternative changed"),
            }
        }
    }
}
