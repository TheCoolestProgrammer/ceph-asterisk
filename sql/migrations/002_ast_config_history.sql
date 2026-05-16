CREATE TABLE ast_config_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    instance_id INT NOT NULL,
    filename VARCHAR(128) NOT NULL,
    version INT NOT NULL,
    config_snapshot TEXT NOT NULL,
    description VARCHAR(512) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    author VARCHAR(128) NOT NULL,
    CONSTRAINT uq_ast_config_history_instance_file_version
        UNIQUE (instance_id, filename, version),
    INDEX idx_ast_config_history_instance_filename (instance_id, filename)
);
