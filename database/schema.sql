CREATE TABLE IF NOT EXISTS reminders (
                    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                    `title` TEXT NOT NULL,
                    `time` TEXT NOT NULL,
                    `interval` TEXT,
                    `channel` INTEGER NOT NULL,
                    `mention` INTEGER,
                    `user_id` INTEGER,
                    `message` TEXT
                )