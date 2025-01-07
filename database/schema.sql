CREATE TABLE IF NOT EXISTS reaction_roles (
                    message_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    emoji TEXT NOT NULL,
                    role_id BIGINT NOT NULL,
                    guild_id BIGINT NOT NULL,
                    PRIMARY KEY (message_id, emoji)
                );

CREATE TABLE IF NOT EXISTS reminders ( 
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    time TEXT NOT NULL,
                    interval TEXT,
                    channel_id INTEGER,
                    role_id INTEGER,
                    user_id INTEGER,
                    message TEXT
                );

CREATE TABLE IF NOT EXISTS events (
                    message_id BIGINT PRIMARY KEY NOT NULL,
                    channel_id BIGINT NOT NULL,
                    creator_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    activity TEXT NOT NULL,
                );

CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INT REFERENCES events(message_id),
                    user_id BIGINT NOT NULL,
                    time TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    votes INT DEFAULT 0
                );