CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  avatar TEXT,
  bio TEXT,
  pxp INTEGER NOT NULL DEFAULT 0,
  name_changes INTEGER NOT NULL DEFAULT 0,
  password TEXT NOT NULL,
  login_code TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code);
