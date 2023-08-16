from flask_openapi3 import Tag, APIBlueprint
from flask import request
from pydantic import BaseModel, Field
from typing import Optional

tag = Tag(name='book', description="Some Book")

class BookPath(BaseModel):
    id: int = Field(..., description="book ID")

blueprint = APIBlueprint(
    '/book',
    __name__,
    url_prefix='/books',
    abp_tags=[tag],
    doc_ui=True
)

@blueprint.get('/book/<int:id>')
def get_book(path: BookPath):
    """get a book."""
    print("GOT ID:", path)
    return {"code": 0, "message": "ok", "book":"Harry Potter"}
