-- users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(120) NOT NULL,
    password VARCHAR(255),
    bio TEXT,
    avatar VARCHAR(255),
    pxp INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    type VARCHAR(50) NOT NULL,   -- наприклад: 'donate', 'reward', 'purchase'
    created_at TIMESTAMP DEFAULT NOW()
);

-- messages table (чат)
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
