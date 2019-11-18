# -*- coding:utf-8 -*- 

import redis
import six
from elasticsearch import Elasticsearch
from flask import current_app


def get_page(page):
    try:
        page = int(page)
    except ValueError:
        page = 1
    return page if page >= 1 else 1


def get_page_size(page_size):
    if page_size == "all":
        return page_size

    try:
        page_size = int(page_size)
    except (ValueError, TypeError):
        page_size = current_app.config.get("DEFAULT_PAGE_COUNT")
    return page_size if page_size >= 1 else current_app.config.get("DEFAULT_PAGE_COUNT")


def handle_arg_list(arg):
    return list(filter(lambda x: x != "", arg.strip().split(","))) if isinstance(arg, six.string_types) else arg


class RedisHandler(object):
    def __init__(self, flask_app=None, prefix=None):
        self.flask_app = flask_app
        self.prefix = prefix
        self.r = None

    def init_app(self, app):
        self.flask_app = app
        config = self.flask_app.config
        try:
            pool = redis.ConnectionPool(
                max_connections=config.get("REDIS_MAX_CONN"),
                host=config.get("CACHE_REDIS_HOST"),
                port=config.get("CACHE_REDIS_PORT"),
                db=config.get("REDIS_DB"))
            self.r = redis.Redis(connection_pool=pool)
        except Exception as e:
            current_app.logger.warning(str(e))
            current_app.logger.error("init redis connection failed")

    def get(self, key_ids):
        try:
            value = self.r.hmget(self.prefix, key_ids)
        except Exception as e:
            current_app.logger.error("get redis error, {0}".format(str(e)))
            return
        return value

    def _set(self, obj):
        try:
            self.r.hmset(self.prefix, obj)
        except Exception as e:
            current_app.logger.error("set redis error, {0}".format(str(e)))

    def add(self, obj):
        self._set(obj)

    def delete(self, key_id):
        try:
            ret = self.r.hdel(self.prefix, key_id)
            if not ret:
                current_app.logger.warn("[{0}] is not in redis".format(key_id))
        except Exception as e:
            current_app.logger.error("delete redis key error, {0}".format(str(e)))


class ESHandler(object):
    def __init__(self, flask_app=None):
        self.flask_app = flask_app
        self.es = None
        self.index = "cmdb"

    def init_app(self, app):
        self.flask_app = app
        config = self.flask_app.config
        self.es = Elasticsearch(config.get("ES_HOST"))
        if not self.es.indices.exists(index=self.index):
            self.es.indices.create(index=self.index)

    def get_index_id(self, ci_id):
        query = {
            'query': {
                'match': {'ci_id': ci_id}
            },
        }
        res = self.es.search(index=self.index, body=query)
        if res['hits']['hits']:
            return res['hits']['hits'][-1].get('_id')

    def create(self, body):
        return self.es.index(index=self.index, body=body).get("_id")

    def update(self, ci_id, body):
        _id = self.get_index_id(ci_id)

        return self.es.index(index=self.index, id=_id, body=body).get("_id")

    def delete(self, ci_id):
        _id = self.get_index_id(ci_id)

        self.es.delete(index=self.index, id=_id)

    def read(self, query, filter_path=None, sort=None):
        filter_path = filter_path or []
        if filter_path:
            filter_path.append('hits.total')

        if sort:
            query.update(dict(sort=sort))

        res = self.es.search(index=self.index, body=query, filter_path=filter_path)
        return res['hits']['total']['value'], [i['_source'] for i in res['hits']['hits']]
