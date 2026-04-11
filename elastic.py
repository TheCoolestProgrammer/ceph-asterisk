from elasticsearch import AsyncElasticsearch

es = AsyncElasticsearch("http://elasticsearch:9201")

def setup_elastic_pipeline():
    pipeline_body = {
        "description": "Asterisk logs parser",
        "processors": [
            {
                "grok": {
                    "field": "message",
                    "patterns": ["\\[%{TIMESTAMP_ISO8601:log_timestamp}\\] %{WORD:log_level}\\[%{NUMBER:thread_id}\\] %{DATA:module}: %{GREEDYDATA:log_message}"] 
                    # Упростил для примера, используйте полный паттерн выше
                }
            }
        ]
    }
    es.ingest.put_pipeline(id="asterisk-parser", body=pipeline_body)