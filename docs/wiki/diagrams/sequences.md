# Sequence Diagrams

## Workflow: Core Orchestration Loop

This diagram illustrates how the Orchestrator pulls messages, transforms them, handles a potential rate-limit failure, and persists the checkpoint.

```mermaid
sequenceDiagram
    participant User
    participant FastAPI
    participant Orchestrator
    participant SessionManager
    participant Transformer
    participant Telegram
    participant SQLite

    User->>FastAPI: Click "Iniciar"
    FastAPI->>Orchestrator: start_flow()
    Orchestrator->>SQLite: get_current_checkpoint()
    
    loop Every Batch
        Orchestrator->>SessionManager: get_active_client()
        SessionManager-->>Orchestrator: Account 1 Client
        Orchestrator->>Telegram: get_history(offset)
        Telegram-->>Orchestrator: List[Messages]
        
        loop Every Message
            Orchestrator->>Transformer: apply_rules(msg)
            Transformer-->>Orchestrator: mutated_msg
            Orchestrator->>Telegram: send_message(mutated_msg)
            
            alt Success
                Telegram-->>Orchestrator: Success
                Orchestrator->>SQLite: update_checkpoint(msg.id)
            else FloodWaitError
                Telegram-->>Orchestrator: FloodWait(300s)
                Orchestrator->>SessionManager: handle_failover()
                SessionManager-->>Orchestrator: Account 2 Client
                Orchestrator->>Telegram: send_message(mutated_msg)
                Telegram-->>Orchestrator: Success
                Orchestrator->>SQLite: update_checkpoint(msg.id)
            end
        end
    end
```

### Walkthrough

1. **User input** — The operator initiates the pipeline from the dashboard.
2. **Batch Retrieval** — The orchestrator pulls messages from Telegram.
3. **Transformation** — Regex rules are applied locally.
4. **Execution & Failover** — The message is sent. If Telegram throws a `FloodWaitError`, the orchestrator immediately requests the secondary client from the Session Manager and retries.
5. **Persistence** — Once successful, the message ID is saved to SQLite, ensuring that a sudden crash won't cause duplicate sends upon restart.
