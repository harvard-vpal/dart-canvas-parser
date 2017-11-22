import json
import requests
from django.conf import settings
from canvas_sdk.exceptions import (CanvasAPIError, InvalidOAuthTokenError)
from canvas_sdk.methods import courses, pages, quizzes, quiz_questions, \
    enrollments, users, modules
from canvas_sdk.utils import get_all_list_data
from canvas_sdk import RequestContext
import logging


log = logging.getLogger('dart')


CANVAS_SDK_SETTINGS = dict(
    max_retries = 3,
    per_page = 40,
)


class CanvasApi(object):
    def __init__(self, url_base, api_token):
        self.url_base = url_base
        self.api_token = api_token


    def _sdk_call(self, function, **kwargs):
        context = self._get_context(self.api_token)
        return function(context, **kwargs)


    def get_course(self, course_id):
        return self._sdk_call(self._get_course, course_id=course_id)


    @staticmethod
    def _get_course(context, course_id):
        url = "{}/v1/courses/{}?include[]=syllabus_body&include[]=term".format(
            context.base_api_url, course_id
        )
        response = requests.get(
            url, headers={"Authorization": "Bearer {}".format(context.auth_token)}
        )
        if response.status_code != 200:
            if response.status_code == 401 and 'WWW-Authenticate' in response.headers:
                raise InvalidOAuthTokenError(
                    "OAuth Token used to make request to %s is invalid" % response.url)
            raise CanvasAPIError(
                status_code=response.status_code,
                msg=unicode(response.json()),
                error_json=response.json(),
            )
        return response.json()


    def get_pages(self, course_id):
        return self._sdk_call(self._get_pages, course_id=course_id)


    @staticmethod
    def _get_pages(context, course_id):
        page_list = get_all_list_data(
            context, pages.list_pages_courses, course_id
        )
        for page in page_list:
            details = pages.show_page_courses(
                context, course_id, page['url']
            )
            page['body'] = details.json()['body']
        return page_list


    def get_quizzes(self, course_id):
        return self._sdk_call(self._get_quizzes, course_id=course_id)


    @staticmethod
    def _get_quizzes(context, course_id):
        quiz_list = get_all_list_data(
            context, quizzes.list_quizzes_in_course, course_id
        )
        for quiz in quiz_list:
            details = get_all_list_data(
                context, quiz_questions.list_questions_in_quiz,
                course_id=course_id,
                quiz_id=quiz['id']
            )
            quiz['questions'] = details
        return quiz_list


    def _get_context(self, api_token):
        api_config = CANVAS_SDK_SETTINGS.copy()
        api_config['auth_token'] = api_token
        api_config['base_api_url'] = '{}/api'.format(self.url_base)
        return RequestContext(**api_config)
