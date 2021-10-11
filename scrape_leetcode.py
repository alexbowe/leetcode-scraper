import json
import re
import requests
import bs4
import logging
import diskcache
import jsonpickle
import pickle
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

LOGGER = logging.getLogger("LeetCode")
CACHE_FILE = ".cache"
COOKIE_PATH = "cookies.pkl"
PROBLEM_LIST_URL = "https://leetcode.com/api/problems/algorithms/"
PROBLEM_URL_TEMPLATE = "https://leetcode.com/problems/{slug}/"
LOGIN_URL = "https://leetcode.com/accounts/login"

# TODO: See how it works with a locked question
# TODO: Build graph (play with edge definitions, related is bi-directional, but make it directional by ranking in terms of difficulty - level and success rate)
# TODO: Toposort? Pagerank? Test it out - follow each chain and see
# TODO: Simulate 1 hour per problem (or scaled with difficulty), and assume that harder problems with the same tags use the same techniques as predecessors, then collapse and test path


class Problem:
    def __init__(self, data, tags=None, related=None, companies=None):
        self.title = data["stat"]["question__title_slug"]
        self.id = data["stat"]["question_id"]
        self.locked = data["paid_only"]
        self.num_submissions = data["stat"]["total_submitted"]
        self.num_accepted = data["stat"]["total_acs"]
        self.frequency = data["frequency"]
        self.level = data["difficulty"]["level"]
        self.tags = set(tags) if tags else set()
        self.related = set(related) if related else set()
        self.companies = companies if companies else []

    @property
    def acceptance(self):
        return self.num_accepted / self.num_submissions

    @property
    def url(self):
        return PROBLEM_URL_TEMPLATE.format(slug=self.title)

    def __repr__(self):
        return "Problem({}, ...)".format(self.title)


def get_number_asks(x):
    try:
        return int(x.find_all("span")[-1].contents[0])
    except:
        # Some questions are tagged by company manually by LeetCode
        return None


def parse_problem(data, soup):
    get_slug = lambda x: x["href"][10:-1]
    get_tag = lambda x: x["href"][5:-1]
    get_company = lambda x: {"company": x["href"][9:], "times_seen": get_number_asks(x)}
    related_html = soup.find_all("a", {"class": "title__1kvt"})
    tags_html = soup.find_all("a", {"class": "topic-tag__1jni"})
    companies_html = soup.find_all("a", href=re.compile("/company/"))
    related = [get_slug(x) for x in related_html]
    tags = [get_tag(x) for x in tags_html]
    companies = [get_company(x) for x in companies_html]
    return Problem(data, tags=tags, related=related, companies=companies)


def make_problem(driver, data, parser=parse_problem):
    slug = data["stat"]["question__title_slug"]
    driver.get(PROBLEM_URL_TEMPLATE.format(slug=slug))
    WebDriverWait(driver, 20).until(
        EC.invisibility_of_element_located((By.ID, "initial-loading"))
    )
    time.sleep(2)
    # Get current tab page source
    html = driver.page_source
    soup = bs4.BeautifulSoup(html, "html.parser")
    return parse_problem(data, soup)


def init_chrome_driver(cookies=[]):
    options = Options()
    options.add_argument("--headless")

    driver = webdriver.Chrome(options=options, executable_path=ChromeDriverManager().install())
    if cookies:
        driver.get(LOGIN_URL)
        for cookie in cookies:
            driver.add_cookie(cookie)
    return driver


def login():
    browser_cookies = {}

    # TODO: Move cookie handling outside of this
    if os.path.isfile(COOKIE_PATH):
        with open(COOKIE_PATH, 'rb') as f:
            return pickle.load(f)
    else:
        LOGGER.info("Starting Chrome - please log in")
        driver = webdriver.Chrome(executable_path=ChromeDriverManager().install())
        driver.get(LOGIN_URL)

        WebDriverWait(driver, 5 * 60).until(
            lambda driver: driver.current_url.find("login") < 0
        )

    browser_cookies = driver.get_cookies()
    with open(COOKIE_PATH, 'wb') as f:
        pickle.dump(browser_cookies, f)
    LOGGER.info("Login successful")
    
    return browser_cookies


class LeetCode:
    def __init__(self, driver=None, cache=None):
        self._cache = cache or diskcache.Cache(CACHE_FILE)
        self._driver = driver or init_chrome_driver(cookies=login())

    def _problem_dict(self):
        payload = json.loads(requests.get(PROBLEM_LIST_URL).content)
        return {
            x["stat"]["question__title_slug"]: x for x in payload["stat_status_pairs"]
        }

    @property
    def problem_titles(self):
        problems = self._problem_dict()
        return sorted(problems.keys())

    def get_problem(self, title, skip_cache=False):
        cached = not skip_cache and title in self._cache
        source = "cache" if cached else "web"
        LOGGER.info(f"Accessing {title} from {source}")
        if cached:
            return self._cache[title]
        problem = make_problem(self._driver, self._problem_dict()[title])
        self._cache[title] = problem
        return problem

    def problems_iter(self):
        return (self.get_problem(key) for key in self.problem_titles)


def main():
    logging.basicConfig(level=logging.INFO)
    lc = LeetCode()
    print(jsonpickle.dumps(list(lc.problems_iter())))

if __name__ == "__main__":
    main()
