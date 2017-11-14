import datetime
import json
import uuid

from canvas_sdk.exceptions import InvalidOAuthTokenError

from canvas_adapter.models import CanvasUser
from canvas_api import get_all_courses, get_pages, get_quizzes
from dart_common.adapter_utils import strip_html
from dart_sdk.models.canvas_asset import CanvasAsset
from dart_sdk.models.canvas_collection import CanvasCollection
from dart_sdk.models.content_embed import ContentEmbed
from dart_sdk.models.content_source_export import ContentSourceExport
from dart_sdk.models.extended_asset import ExtendedAsset
from dart_sdk.models.extended_collection import ExtendedCollection

import logging

log = logging.getLogger('dart')


class CanvasParser(object):
    def __init__(self, content_source):
        self.content_source = content_source
        self.content_license = content_source.default_license
        self.errors = []
        self.warnings = []
        self.assets = []
        self.collections = []
        self.user_model = CanvasUser.objects.get(
            user_uid=content_source.user_uid
        )

    def parse(self):
        try:
            for course in get_all_courses(self.user_model):
                course_assets = []
                course_assets += self._get_page_assets(course['id'])
                course_assets += self._get_quiz_assets(course['id'])
                self._get_course_collection(course, course_assets)
        except InvalidOAuthTokenError:
            model = CanvasUser.objects.get(
                user_uid=self.content_source.user_uid
            )
            model.api_token = None
            model.save()
        return self._get_export_data()

    def _get_page_assets(self, course_id):
        assets = []
        pages = get_pages(self.user_model, course_id)
        for page in pages:
            uid = unicode(uuid.uuid4())
            if 'last_edited_by' in page and 'display_name' in page[
                'last_edited_by']:
                creator = page['last_edited_by']['display_name']
            else:
                creator = 'Unknown'
            body = strip_html(page['body']) if page['body'] else ''
            content_embed = [
                ContentEmbed(
                    data=self._get_page_api_url(course_id, page['page_id']),
                    is_default=True,
                    protocol='canvas_page',
                )
            ]
            if body:
                content_embed.append(ContentEmbed(
                    data=page['body'],
                    is_default=False,
                    protocol='html',
                ))
            # print "Page: {}".format(json.dumps(page))
            assets.append(ExtendedAsset(
                asset=CanvasAsset(
                    canvas_id=page['page_id'],
                    citation_url=page['html_url'],
                    content_creator=creator,
                    content_embed=content_embed,
                    content_license=self.content_license,
                    content_source=self.content_source,
                    content_type=u'html',
                    graded=False,
                    preview_images=[],
                    publish_date=page['updated_at'],
                    title=page['title'],
                    uid=uid,
                    description=page['title'] if page[
                        'title'] else 'Canvas Page',
                    duration=None,
                ),
                search_text=body,
                original_content=page['body'],
                uid=uid,
                index_for_search=False,
                index_for_recommendation=False,
            ))
        self.assets += assets
        return assets

    def _get_quiz_assets(self, course_id):
        assets = []
        quizzes = get_quizzes(self.user_model, course_id)
        for quiz in quizzes:
            uid = unicode(uuid.uuid4())
            assets.append(ExtendedAsset(
                asset=CanvasAsset(
                    canvas_id=quiz['id'],
                    citation_url=quiz['html_url'],
                    content_creator='Unknown',
                    content_embed=[ContentEmbed(
                        data=self._get_quiz_api_url(course_id, quiz['id']),
                        is_default=True,
                        protocol='canvas_quiz',
                    )],
                    content_license=self.content_license,
                    content_source=self.content_source,
                    content_type=u'problem',
                    graded=True,
                    preview_images=[],
                    publish_date=None,
                    title=quiz['title'],
                    uid=uid,
                    description=quiz['description'] if quiz[
                        'description'] else 'Canvas Quiz',
                    duration=None,
                ),
                search_text=_get_quiz_search_text(quiz),
                original_content=json.dumps(quiz),
                uid=uid,
                index_for_search=False,
                index_for_recommendation=False,
            ))
        self.assets += assets
        return assets

    def _get_course_collection(self, course, course_assets):
        uid = unicode(uuid.uuid4())
        publish_date = course['term']['start_at']
        if not publish_date:
            publish_date = datetime.datetime.now().isoformat()
        self.collections.append(ExtendedCollection(
            collection=CanvasCollection(
                canvas_id=course['id'],
                citation_url="{}/courses/{}".format(
                    self.content_source.canvas_api_base, course['id']
                ),
                content_creator='Unknown',
                content_source=self.content_source,
                content_type='course',
                ordered='false',
                preview_images=[],
                publish_date=publish_date,
                title=course['name'],
                description=course['name'],
                uid=uid,
            ),
            asset_uids=[a.uid for a in course_assets],
            collection_uids=[],
            parent_collections=[],
            uid=uid,
        ))

    def _get_export_data(self):
        return ContentSourceExport(
            content_source=self.content_source,
            assets=self.assets,
            collections=self.collections,
        )

    def _get_page_api_url(self, course_id, page_id):
        return u'{}/v1/courses/{}/pages/{}'.format(
            self.content_source.canvas_api_base, course_id,
            page_id
        )

    def _get_quiz_api_url(self, course_id, quiz_id):
        return u'{}/v1/courses/{}/quizzes/{}'.format(
            self.content_source.canvas_api_base, course_id,
            quiz_id
        )


def _get_quiz_search_text(quiz):
    text = u"{}\n{}".format(quiz.get('title', ''), quiz.get('description', ''))
    for question in quiz.get('questions', []):
        text = u"{}\n{}".format(text, question.get('question_text', ''))
        for answer in question.get('answers', []):
            text = u"{}\n{}".format(text, answer.get('text', ''))
    return text