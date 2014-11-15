import json
import sys

from django.http import HttpResponse
from django.views.decorators.cache import cache_page
from django.core.cache import cache

from django.contrib.auth.models import User

from allauth.socialaccount.models import SocialToken
from allauth.socialaccount.models import SocialAccount

from xbook.ajax.models import Subject, SubjectPrereq
from xbook.front.models import UserSubject

from collections import deque
from facepy import GraphAPI

BOOKMARKED = "Bookmarked"
COMPLETED = "Completed"
STUDYING = "Studying"
PLANNED = "Planned"


def devlog(data):
    print >> sys.stderr, data


def AJAX(*args, **kwargs):
    resp = HttpResponse(*args, **kwargs)
    resp["Access-Control-Allow-Origin"] = "*"
    resp["Access-Control-Allow-Methods"] = "GET, POST"
    resp["Access-Control-Max-Age"] = "1000"
    resp["Access-Control-Allow-Headers"] = "*"
    return resp


def JSON(hash, *args, **kwargs):
    return AJAX(json.dumps(hash), *args, content_type="application/json", **kwargs)


def presentSubject(subj, root=False):
    return {
        "code": subj.code,
        "name": subj.name,
        "url": subj.link,
        "root": root,
        "credit": str(subj.credit),
        "commenceDate": subj.commence_date,
        "timeCommitment": subj.time_commitment,
        "overview": subj.overview,
        "objectives": subj.objectives,
        "assessment": subj.assessment,
        "prereq": subj.prerequisite,
        "coreq": subj.corequisite
    }


def presentFriend(socialAccount, **details):
    info = {
        "avatarUrl": socialAccount.get_avatar_url(),
        "fbUrl": socialAccount.get_profile_url(),
        "fullname": socialAccount.user.get_full_name(),
        "username": socialAccount.user.username
    }
    info.update(**details)

    return info


def get_friends_info(localFriends, subjectCode):
    friendsInfo = []

    users = map(lambda friend: friend.user, localFriends)
    userSubjects = UserSubject.objects.filter(user__in=users, subject__code=subjectCode)
    states = { item.user.id: item.state for item in userSubjects }

    for friend in localFriends:
        if not friend.user.id in states:
            continue
        friendsInfo.append(
            presentFriend(
                friend,
                state = states[friend.user.id]
            )
        )

    return friendsInfo


@cache_page(60 * 60 * 4)
def social_statistics(request, subjectCode):
    friendUIDs = set(get_friend_uids(request.user) or [])

    if not friendUIDs: return JSON({ "friends": [] })

    localFriends = SocialAccount.objects.filter(uid__in=friendUIDs, provider="facebook")

    return JSON({
        "friends": get_friends_info(localFriends, subjectCode)
    })


def get_friend_uids(user):
    friendsCacheKey = 'friend-ids-of-{}'.format(user.id)
    friendUIDs = cache.get(friendsCacheKey)

    if friendUIDs: return friendUIDs

    if user.is_authenticated():
        try:
            tokens = SocialToken.objects.get(account__user=user, account__provider="facebook")
            fb_graph = GraphAPI(tokens)
            friendUIDs = map(lambda f: f["id"], fb_graph.get("me/friends").get("data"))
            cache.set(friendsCacheKey, friendUIDs, timeout=60 * 60)
        except SocialAccount.DoesNotExist:
            return None
    return friendUIDs


def attach_user_info(nodeInfo, subj, user):
    if not user.is_authenticated() or \
        not len(UserSubject.objects.filter(user=user, subject=subj)):
        nodeInfo.update({"hasCompleted": False})
    else:
        user_subject = UserSubject.objects.filter(user=user, subject=subj)[0]
        nodeInfo.update(
            state = user_subject.state,
            hasCompleted = True,
            yearCompleted = user_subject.year,
            semesterCompleted = user_subject.semester
        )


@cache_page(60 * 60)
def subject_graph(request, uni, code, prereq=True):
    nodes, links = [], []
    graph = { "nodes": nodes, "links": links }
    subjQueue = deque()

    try:
        subject = Subject.objects.get(code=code)
        subjQueue.append(subject)
    except Subject.DoesNotExist:
        return graph

    queryKey = prereq and "subject__code" or "prereq__code"
    queryParam = {}
    subjectRelation = prereq and \
        (lambda source, target: { "source": source, "target": target }) or \
        (lambda target, source: { "source": source, "target": target })
    relationGetter = prereq and \
        (lambda relation: relation.prereq) or \
        (lambda relation: relation.subject)

    parentIndex, codeToIndex = -1, { subject.code: 0 }
    while subjQueue:
        subj = subjQueue.popleft()

        nodeInfo = presentSubject(subj, root=(parentIndex == -1))

        attach_user_info(nodeInfo, subj, request.user)
        nodes.append(nodeInfo)

        parentIndex += 1
        queryParam[queryKey] = subj.code
        relations = SubjectPrereq.objects.filter(**queryParam)

        for relation in relations:
            seen = True
            related = relationGetter(relation)
            if not related.code in codeToIndex:
                seen = False
                codeToIndex[related.code] = len(codeToIndex)
            links.append(subjectRelation(parentIndex, codeToIndex[related.code]))
            if not seen:
                subjQueue.append(related)

    return JSON(graph)


@cache_page(60 * 60 * 24)
def subject_list(request, uni):
    l = []
    subjList = { "subjList": l }

    for subj in Subject.objects.only("code", "name").iterator():
        l.append({ "code": subj.code, "name": subj.name })

    return JSON(subjList)


@cache_page(60 * 60 * 4)
def subject_statistics(request, subjectCode):
    userSubjects = UserSubject.objects.filter(subject__code=subjectCode)

    return JSON({
        "planned": userSubjects.filter(state=PLANNED).count(),
        "studying": userSubjects.filter(state=STUDYING).count(),
        "completed": userSubjects.filter(state=COMPLETED).count(),
        "bookmarked": userSubjects.filter(state=BOOKMARKED).count()
    })


def name_or_account(user):
    if user.first_name and user.last_name:
        return user.first_name + " " + user.last_name
    elif user.first_name:
        return user.first_name
    elif user.last_name:
        return user.last_name
    else:
        return user.username


def attach_userinfo_node(user):
    user = name_or_account(user)

    return {
        "code": user,
        "name": user,
        "root": True,
        "credit": "",
        "commenceDate": "",
        "timeCommitment": "",
        "overview": "",
        "objectives": "",
        "assessment": "",
        "prereq": "",
        "coreq": "",
        "isUserNode": True,
        "hasCompleted": False,
        "yearCompleted": 0,
        "semesterCompleted": "",
        "state": ""
    }


def get_user_subject(request, username):
    nodes, links = [], []
    graph = { "nodes": nodes, "links": links }

    if not len(User.objects.filter(username=username)):
        return JSON(graph)

    selected_user = User.objects.get(username=username)
    user_subjects = selected_user.user_subject.all()

    parent_index = -1
    for user_subject in user_subjects:
        subj = user_subject.subject

        nodeInfo = presentSubject(subj)

        attach_user_info(nodeInfo, subj, selected_user)
        nodes.append(nodeInfo)

        parent_index += 1
        relations = SubjectPrereq.objects.filter(subject__code=subj.code)

        for relation in relations:
            compare_index = 0
            for taken_subject in user_subjects:
                related = relation.prereq
                if taken_subject.subject.code == related.code:
                    links.append({ "source": parent_index, "target": compare_index })
                compare_index += 1

    nodes.append(attach_userinfo_node(selected_user))

    return JSON(graph)
