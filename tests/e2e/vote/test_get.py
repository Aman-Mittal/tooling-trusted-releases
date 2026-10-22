# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import e2e.vote.helpers as helpers  # type: ignore[reportMissingImports]
from playwright.sync_api import Page, expect


def test_browse_files_link_visible(page_vote: Page) -> None:
    """The browse files link should be visible."""
    browse_link = page_vote.locator('a:has-text("Browse files")')
    expect(browse_link).to_be_visible()


def test_curl_command_contains_expected_text(page_vote: Page) -> None:
    """The curl command should contain the expected curl invocation."""
    command_text = helpers.get_curl_command_text(page_vote)
    expect(command_text).to_contain_text("curl -fsS https://")
    expect(command_text).to_contain_text("| sh")


def test_curl_copy_button_restores_original_text(page_vote: Page) -> None:
    """The curl copy button should restore original text after feedback."""
    copy_button = helpers.get_curl_copy_button(page_vote)
    copy_button.click()

    expect(copy_button).to_contain_text("Copy", timeout=5000)


def test_curl_copy_button_shows_copied_feedback(page_vote: Page) -> None:
    """Clicking the curl copy button should show Copied feedback."""
    copy_button = helpers.get_curl_copy_button(page_vote)
    expect(copy_button).to_contain_text("Copy")

    copy_button.click()

    expect(copy_button).to_contain_text("Copied!")


def test_curl_copy_button_visible(page_vote: Page) -> None:
    """The curl copy button should be visible on the vote page."""
    copy_button = helpers.get_curl_copy_button(page_vote)
    expect(copy_button).to_be_visible()


def test_download_zip_button_visible(page_vote: Page) -> None:
    """The download ZIP button should be visible for authenticated users."""
    zip_button = page_vote.locator('a:has-text("Download all (ZIP)")')
    expect(zip_button).to_be_visible()


def test_page_has_checks_section(page_vote: Page) -> None:
    """The vote page should have a checks section."""
    checks_heading = page_vote.locator("h2#checks")
    expect(checks_heading).to_be_visible()
    expect(checks_heading).to_contain_text("Review file checks")


def test_page_has_download_section(page_vote: Page) -> None:
    """The vote page should have a download section."""
    download_heading = page_vote.locator("h2#download")
    expect(download_heading).to_be_visible()
    expect(download_heading).to_contain_text("Download")


def test_page_has_vote_section(page_vote: Page) -> None:
    """The vote page should have a vote section."""
    vote_heading = page_vote.locator("h2#vote")
    expect(vote_heading).to_be_visible()
    expect(vote_heading).to_contain_text("Cast your vote")


def test_rsync_command_contains_expected_text(page_vote: Page) -> None:
    """The rsync command should contain the expected rsync invocation."""
    command_text = helpers.get_rsync_command_text(page_vote)
    expect(command_text).to_contain_text("rsync -av")
    # We don't include the port since that can be configured
    expect(command_text).to_contain_text("-e 'ssh -p")


def test_rsync_copy_button_restores_original_text(page_vote: Page) -> None:
    """The rsync copy button should restore original text after feedback."""
    copy_button = helpers.get_rsync_copy_button(page_vote)
    copy_button.click()

    expect(copy_button).to_contain_text("Copy", timeout=5000)


def test_rsync_copy_button_shows_copied_feedback(page_vote: Page) -> None:
    """Clicking the rsync copy button should show Copied feedback."""
    copy_button = helpers.get_rsync_copy_button(page_vote)
    expect(copy_button).to_contain_text("Copy")

    copy_button.click()

    expect(copy_button).to_contain_text("Copied!")


def test_rsync_copy_button_visible(page_vote: Page) -> None:
    """The rsync copy button should be visible for authenticated users."""
    copy_button = helpers.get_rsync_copy_button(page_vote)
    expect(copy_button).to_be_visible()


def test_vote_buttons_visible(page_vote: Page) -> None:
    """The vote decision buttons should be visible."""
    plus_one = page_vote.locator('label[for="decision_0"]')
    zero = page_vote.locator('label[for="decision_1"]')
    minus_one = page_vote.locator('label[for="decision_2"]')

    expect(plus_one).to_be_visible()
    expect(zero).to_be_visible()
    expect(minus_one).to_be_visible()
