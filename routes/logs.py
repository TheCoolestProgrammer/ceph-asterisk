from typing import Optional

from fastapi import APIRouter
from schemas.logs import LogsModel
from elasticsearch import NotFoundError
from elasticsearch import AsyncElasticsearch

router = APIRouter(prefix="/logs")

# Подключаемся к Elastic (внутри Docker используй имя сервиса)
es = AsyncElasticsearch("http://elasticsearch:9200")

@router.get("/", response_model=LogsModel)
async def get_logs(page: int = 0, limit: int = 5, level: Optional[str] = None, pbx_id: Optional[str] = None, text: Optional[str] = None):
    offset = page * limit

    query = {"bool": {"must": [], "filter": []}}

    if text:
        query["bool"]["must"].append({"match_phrase": {"asterisk.message": text}})

    if level:
        query["bool"]["filter"].append({"term": {"asterisk.level.keyword": level}})

    if pbx_id:
        query["bool"]["filter"].append({"term": {"pbx_id.keyword": pbx_id}})

    if not query["bool"]["must"] and not query["bool"]["filter"]:
        query = {"match_all": {}}

    try:
        response = await es.search(
            index="raw-asterisk-logs",
            body={
                "from": offset,
                "size": limit,
                "query": query,
                "sort": [{"@timestamp": {"order": "desc"}}]
            }
        )
    except NotFoundError:
        # Индекс ещё не создан, Filebeat не отправил логи
        return {"status": "success", "data": [], "total": 0}

    logs = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]

        logs.append({
            "message": {
                "timestamp": source.get("asterisk", {}).get("timestamp") or source.get("@timestamp"),
                "level": source.get("asterisk", {}).get("level", "UNKNOWN"),
                "pid": source.get("asterisk", {}).get("pid"),
                "file": source.get("asterisk", {}).get("file"),
                "message": source.get("asterisk", {}).get("message", source.get("message", ""))
            },
            "pbx_id": source.get("pbx_id")
        })

    return {"status": "success", "data": logs, "total": response["hits"]["total"]["value"]}


