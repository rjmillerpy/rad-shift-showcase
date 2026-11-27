"""The "AI-generated" label on posts (product roadmap Phase 2, AI content detection)."""

import pytest

import app.posts.uploads as uploads
from tests.helpers import jpeg_with_c2pa_segment, jpeg_with_xmp, real_image


def _post(client, headers, files=None, **form):
    return client.post(
        "/posts/add", data={"text": "look at this", **form}, files=files, headers=headers
    )


def _label(client):
    return client.get("/posts/").json()["posts"][0]["ai_label"]


@pytest.fixture()
def author(create_user, auth_header):
    create_user(username="author")
    return auth_header("author")


def test_the_author_can_say_it_was_made_with_ai(client, author):
    assert _post(client, author, ai_generated="true").status_code == 200
    assert _label(client) == "author"


@pytest.mark.parametrize(
    "image",
    [jpeg_with_xmp("trainedAlgorithmicMedia"), jpeg_with_c2pa_segment()],
    ids=["xmp", "c2pa"],
)
def test_an_image_whose_credentials_say_ai_labels_the_post(client, author, image):
    upload = uploads.upload_fileobj_to_s3
    upload.reset_mock()

    assert (
        _post(client, author, files={"image": ("art.jpg", image, "image/jpeg")}).status_code == 200
    )

    assert _label(client) == "content_credentials"
    # The marker went with the rest of the metadata; the label is what remains.
    (call,) = upload.call_args_list
    assert b"AlgorithmicMedia" not in call.args[0].getvalue()


def test_the_authors_own_word_comes_first(client, author):
    image = jpeg_with_xmp("trainedAlgorithmicMedia")
    _post(client, author, files={"image": ("art.jpg", image, "image/jpeg")}, ai_generated="true")
    assert _label(client) == "author"


@pytest.mark.parametrize(
    "files",
    [None, {"image": ("photo.jpg", real_image(), "image/jpeg")}],
    ids=["text", "plain-photo"],
)
def test_otherwise_no_label(client, author, files):
    _post(client, author, files=files)
    assert _label(client) is None
