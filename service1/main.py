from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from schema import schema
from database import init_db

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    await init_db()


graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")
