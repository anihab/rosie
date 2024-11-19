CREATE TABLE IF NOT EXISTS reaction_roles (
                    `message_id` BIGINT NOT NULL,
                    `emoji` TEXT NOT NULL,
                    `role_id` BIGINT NOT NULL,
                    `guild_id` BIGINT NOT NULL,
                    PRIMARY KEY (`message_id`, `emoji`)
                );

CREATE TABLE IF NOT EXISTS reminders ( 
                    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                    `title` TEXT NOT NULL,
                    `time` TEXT NOT NULL,
                    `interval` TEXT,
                    `channel_id` INTEGER,
                    `role_id` INTEGER,
                    `user_id` INTEGER,
                    `message` TEXT
                );