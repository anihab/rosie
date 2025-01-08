CREATE TABLE IF NOT EXISTS reaction_roles (
                    message_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    emoji TEXT NOT NULL,
                    role_id BIGINT NOT NULL,
                    guild_id BIGINT NOT NULL,
                    PRIMARY KEY (message_id, emoji)
                );

CREATE TABLE IF NOT EXISTS reminders ( 
                    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    time TEXT NOT NULL,
                    interval TEXT,
                    channel_id BIGINT,
                    role_id BIGINT,
                    user_id BIGINT,
                    message TEXT
                );

CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    creator_id BIGINT NOT NULL,
                    role_id BIGINT,
                    activity TEXT NOT NULL
                );

CREATE TABLE IF NOT EXISTS suggestions (
                    event_id INTEGER NOT NULL,
                    time TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    PRIMARY KEY (event_id, emoji),
                    FOREIGN KEY (event_id) REFERENCES events (event_id) ON DELETE CASCADE
                );