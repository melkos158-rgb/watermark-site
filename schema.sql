CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    name TEXT,
    avatar_url TEXT,
    about TEXT,
    pxp INTEGER NOT NULL DEFAULT 0,
    code TEXT
);
