from datetime import datetime

from fastapi import APIRouter
import re
from schemas.logs import LogsModel

router = APIRouter(prefix="/logs")

from elasticsearch import AsyncElasticsearch

# from elastic import es
# Подключаемся к Elastic (внутри Docker используй имя сервиса)
es = AsyncElasticsearch("http://elasticsearch:9200")

def parse_asterisk_log(raw_message: str):
    # Регулярное выражение для формата:
    # [2026-04-11 17:15:00] VERBOSE[888] chan_sip.c: Текст сообщения
    pattern = r"\[(?P<timestamp>.*?)\] (?P<level>\w+)\[(?P<pid>\d+)\] (?P<source>.*?): (?P<msg>.*)"
    
    match = re.match(pattern, raw_message)
    
    if match:
        data = match.groupdict()
        # Можно сразу превратить строку с датой в объект datetime для сортировки
        try:
            data['timestamp'] = datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass # Если формат даты вдруг другой, оставляем строкой
            
        return data
    
    # Если строка не подошла под формат (например, системное сообщение), 
    # возвращаем её как есть в поле msg
    return {
        "timestamp": None,
        "level": "UNKNOWN",
        "pid": None,
        "source": "system",
        "msg": raw_message
    }

@router.get("/",response_model=LogsModel)
async def get_logs( page: int=0, limit: int = 5):
    offset = page * limit

    response = await es.search(
        index="*asterisk*", 
        body={
            "from": offset,
            "size": limit,    
            "query": {"match_all": {}},
            "sort": [{"@timestamp": {"order": "desc"}}]
        }
    )
    # return response
    logs = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        message = source.get("message")
        
        logs.append({
            # "timestamp": source.get("@timestamp"),
            "message":parse_asterisk_log(message), 
            "pbx_id": source.get("pbx_id")
        })
    
        
    return {"status": "success", "data": logs, "total":response["hits"]["total"]["value"]}


