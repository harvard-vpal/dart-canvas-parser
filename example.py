# example for using dart_canvas_parser package
from dart_canvas_parser.parser import CanvasParser
from dart_sdk.models.canvas_content_source import CanvasContentSource

import secure

content_source = CanvasContentSource(
    default_license = {
            'text_url':'PLACEHOLDER',
            'name': 'PLACEHOLDER',
            'uid': 'PLACEHOLDER'
        },
    uid = 'PLACEHOLDER',
    user_uid = 'PLACEHOLDER',
)

canvas_parser = CanvasParser(content_source, secure.CANVAS_URL_BASE, secure.CANVAS_API_TOKEN)

parsed = canvas_parser.parse(course_ids=[secure.CANVAS_COURSE_ID])
