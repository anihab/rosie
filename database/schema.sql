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
                    eventID INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    creator TEXT NOT NULL,
                    role TEXT,
                    activity TEXT NOT NULL,
                );

CREATE TABLE IF NOT EXISTS suggestions (
                    eventID INTEGER NOT NULL,
                    suggestionID INTEGER AUTOINCREMENT,
                    time TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    votes INTEGER DEFAULT 0,
                    PRIMARY KEY (eventID, suggestionID),
                    FOREIGN KEY (eventID) REFERENCES events (eventID) ON DELETE CASCADE
                );