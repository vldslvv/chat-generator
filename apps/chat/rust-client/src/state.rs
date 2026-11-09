use crate::{protocol::User, transport::Connection};
use chrono::{DateTime, Utc};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ConnectionState {
    Disconnected,
    Connecting,
    Connected,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum SessionState {
    None,
    LoginPending,
    LoggedIn,
}

pub struct ClientState {
    pub server_url: String,
    pub connection: Option<Connection>,
    pub connection_state: ConnectionState,
    pub session_state: SessionState,
    pub login_username: Option<String>,
    pub authenticated_user: Option<User>,
    pub remembered_username: Option<String>,
    pub last_heartbeat_at: Option<DateTime<Utc>>,
}

pub fn initial(server_url: String) -> ClientState {
    ClientState {
        server_url,
        connection: None,
        connection_state: ConnectionState::Disconnected,
        session_state: SessionState::None,
        login_username: None,
        authenticated_user: None,
        remembered_username: None,
        last_heartbeat_at: None,
    }
}

pub fn disconnected(state: &mut ClientState) {
    state.connection = None;
    state.connection_state = ConnectionState::Disconnected;
    state.session_state = SessionState::None;
    state.login_username = None;
    state.authenticated_user = None;
}

pub fn logged_in(state: &mut ClientState, user: User) {
    state.remembered_username = Some(user.name.clone());
    state.authenticated_user = Some(user);
    state.login_username = None;
    state.session_state = SessionState::LoggedIn;
}
