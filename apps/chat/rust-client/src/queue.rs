use crate::transport;
use std::collections::VecDeque;
use uuid::Uuid;

pub struct QueuedMessage {
    pub sender_name: String,
    pub recipient: String,
    pub text: String,
    pub correlation_id: Option<Uuid>,
}

pub type OutgoingQueue = VecDeque<QueuedMessage>;

pub fn enqueue(queue: &mut OutgoingQueue, sender_name: String, recipient: String, text: String) {
    queue.push_back(QueuedMessage {
        sender_name,
        recipient,
        text,
        correlation_id: None,
    });
}

pub fn accept(queue: &mut OutgoingQueue, correlation: Uuid) -> bool {
    if let Some(index) = queue
        .iter()
        .position(|entry| entry.correlation_id == Some(correlation))
    {
        queue.remove(index);
        true
    } else {
        false
    }
}

pub fn reset_attempts(queue: &mut OutgoingQueue) {
    for entry in queue {
        entry.correlation_id = None;
    }
}

pub fn current_correlation(queue: &OutgoingQueue) -> Option<Uuid> {
    queue.iter().find_map(|entry| entry.correlation_id)
}

pub fn flush_messages(
    queue: &mut OutgoingQueue,
    sender_name: &str,
    connection: &mut transport::Connection,
) -> Result<(), (Uuid, String)> {
    for entry in queue {
        if entry.sender_name != sender_name || entry.correlation_id.is_some() {
            continue;
        }
        let correlation = Uuid::new_v4();
        entry.correlation_id = Some(correlation);
        transport::send_message(
            connection,
            correlation,
            entry.recipient.clone(),
            entry.text.clone(),
        )
        .map_err(|cause| (correlation, cause))?;
    }
    Ok(())
}
