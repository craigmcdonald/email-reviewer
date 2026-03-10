"""Shared pagination helper."""

import math


def paginate_result(items, total: int, page: int, per_page: int | None):
    if per_page:
        pages = math.ceil(total / per_page)
    else:
        pages = 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
