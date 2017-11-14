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


def _sdk_call(user_model, function, **kwargs):
    if user_model.refresh_token and not user_model.api_token:
        log.info("No API token for user {}".format(user_model.user_uid))
        _refresh_api_token(user_model)
    context = _get_context(user_model.api_token)
    try:
        return function(context, **kwargs)
    except InvalidOAuthTokenError:
        log.info(
            "Invalid or expired API token for user {}".format(
                user_model.user_uid)
        )
        _refresh_api_token(user_model)
        context = _get_context(user_model.api_token)
        return function(context, **kwargs)


def _refresh_api_token(user_model):
    user_model.api_token = None
    try:
        if user_model.refresh_token:
            url = '{}/login/oauth2/token'.format(settings.CANVAS_URL_BASE)
            log.info("Refreshing token from URL {}".format(url))
            data = {
                'grant_type': 'refresh_token',
                'client_id': settings.CANVAS_OAUTH_CLIENT_ID,
                'client_secret': settings.CANVAS_OAUTH_CLIENT_KEY,
                'refresh_token': user_model.refresh_token
            }
            headers = {
                'Content-Type': 'application/json',
            }
            response = requests.post(url, json.dumps(data), headers=headers)
            if response.status_code != 200:
                raise CanvasAPIError(
                    status_code=response.status_code,
                    msg=u"Error from {}: {}".format(url, response.text)
                )
            user_model.api_token = response.json()['access_token']
            log.info(
                "Refreshed API token for user {}".format(user_model.user_uid)
            )
    finally:
        user_model.save()


def check_token(user_model):
    return _sdk_call(user_model, _check_token)


def _check_token(context):
    log.info("Getting profile")
    users.get_user_profile(context, 'self').json()
    log.info("Fetched profile")
    return True


def get_all_courses(user_model):
    return _sdk_call(user_model, _get_all_courses)


def _get_all_courses(context):
    lst = get_all_list_data(
        context,
        enrollments.list_enrollments_users,
        user_id='self',
        state='completed',
        type=['TeacherEnrollment', 'TaEnrollment', 'ObserverEnrollment',
              'DesignerEnrollment'],
    )
    lst += get_all_list_data(
        context,
        enrollments.list_enrollments_users,
        user_id='self',
        state='active',
        type=['TeacherEnrollment', 'TaEnrollment', 'ObserverEnrollment',
              'DesignerEnrollment'],
    )
    course_list = []
    for e in lst:
        course_list.append(_get_course(context, e['course_id']))
    return course_list


def get_active_courses(user_model):
    """
    Makes an SDK call (_sdk_call transforms user model into canvas_python_sdk
    request context)
    :param user_model: instance of canvas_adapter.models.CanvasUser
    :return: results of _get_active_courses()
    """
    return _sdk_call(user_model, _get_active_courses)


def _get_active_courses(context):
    """
    Gets a full list of courses for which the user has a teacher or designer
    role and which are either unpublished or available (i.e. not completed or
    deleted).
    :param context: request context required by canvas_python_sdk
    :return: list of dicts representing Canvas courses (see
    https://canvas.instructure.com/doc/api/courses.html#Course)
    """
    lst = get_all_list_data(
        context,
        courses.list_your_courses,
        include='term',
        state=['unpublished', 'available']
    )
    course_list = []
    for c in lst:
        for e in c['enrollments']:
            if e['type'] in ['teacher', 'designer']:
                course_list.append(c)
                break
    log.info("Found {} active courses.".format(len(course_list)))
    return course_list


def get_course(user_model, course_id):
    return _sdk_call(user_model, _get_course, course_id=course_id)


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


def get_pages(user_model, course_id):
    return _sdk_call(user_model, _get_pages, course_id=course_id)


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


def get_quizzes(user_model, course_id):
    return _sdk_call(user_model, _get_quizzes, course_id=course_id)


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


def get_default_module_id(user_model, course_id):
    return _sdk_call(user_model, _get_default_module_id, course_id=course_id)


def _get_default_module_id(context, course_id):
    module_list = get_all_list_data(context, modules.list_modules,
                                    course_id, 'items')
    module_id = next((x['id'] for x in module_list if x.get(
        'name', None) == settings.CANVAS_IMPORT_MODULE_NAME), None)
    if not module_id:
        response = modules.create_module(context, course_id,
                                         settings.CANVAS_IMPORT_MODULE_NAME)
        module_id = response.json()['id']
    return module_id


def create_url_module_item(user_model, course_id, module_id, url, title):
    return _sdk_call(
        user_model, _create_url_module_item,
        course_id=course_id, module_id=module_id, url=url, title=title
    )


def _create_url_module_item(context, course_id, module_id, url, title):
    modules.create_module_item(
        request_ctx=context,
        course_id=course_id,
        module_id=module_id,
        module_item_type='ExternalUrl',
        module_item_content_id=None,
        module_item_external_url=url,
        module_item_title=title
    )


def _get_context(api_token):
    api_config = settings.CANVAS_SDK_SETTINGS.copy()
    api_config['auth_token'] = api_token
    return RequestContext(**api_config)
