import os
import json
import requests
import unicodedata

from bs4 import BeautifulSoup


def save_json(obj, path):
    with open(path, "w") as fp:
        json.dump(obj, fp)


def load_json(path):
    with open(path, "r") as fp:
        obj = json.load(fp)
    return obj


TEMP_DIR = "C:/Temp/CRR_parser"
os.makedirs(TEMP_DIR, exist_ok=True)

EBA_WEBSITE = "https://www.eba.europa.eu"
CRR_HOMEPAGE = EBA_WEBSITE + "/regulation-and-policy/single-rulebook/interactive-single-rulebook/108255"


class CRR():
    def __init__(self, load_cached=True, always_save=True):

        self.crr_index_path = os.path.join(TEMP_DIR, "crr_index.json")
        if os.path.isfile(self.crr_index_path) and load_cached:
            print("Loading")
            self.__dict__ = load_json(self.crr_index_path)
        else:
            print("Creating")
            self.articles_objs = self.load_index()

        self.always_save = always_save
        self.save()

    @staticmethod
    def get_article_dict(a_object, base_url=EBA_WEBSITE):
        artic_dict = {}
        text = unicodedata.normalize("NFKD", a_object.text.strip())
        artic_dict['text'] = text
        artic_dict['url'] = base_url + a_object["href"]
        artic_dict['article_num'] = text.split(":")[0].replace("Article", "").strip()
        artic_dict['article_title'] = text.split(":")[1].strip()
        artic_dict['body_lines'] = None
        return artic_dict

    @staticmethod
    def get_article_body(article_dict, footnotes=False):
        if article_dict['body_lines'] is None:
            print(f"Getting Article {article_dict['article_num']} online")
            article_soup = BeautifulSoup(requests.get(article_dict['url']).text, 'html.parser')
            line_objects = (article_soup
                            .find(lambda tag: tag.name == "div" and tag.text.startswith("Main content:"))
                            .parent.findChildren("div", recursive=False)[1]
                            .findChildren(recursive=False)[0].findChildren(recursive=False)
                            )
            article_dict['body_lines'] = [unicodedata.normalize("NFKD", line.text.replace("\n", " ")) for line in
                                          line_objects
                                          if (line.get("id", "") != "footnotes") or footnotes]
        return article_dict['body_lines']

    def load_index(self):
        html_text = requests.get(CRR_HOMEPAGE).text
        soup = BeautifulSoup(html_text, 'html.parser')
        all_articles = soup.find_all("a", attrs={"text-type": "Article"})
        all_articles_objs = {}
        for article in all_articles:
            a = self.get_article_dict(article)
            all_articles_objs[a['article_num']] = a
        return all_articles_objs

    def save(self):
        save_json(self.__dict__, self.crr_index_path)

    def __getitem__(self, item):
        article = self.articles_objs.get(str(item))
        if article is None:
            raise ValueError("Could not find article. Use crr.list_articles() for full list of articles.")
        a = self.get_article_body(article, footnotes=False)
        if self.always_save:
            self.save()
        return a

    def list_articles(self):
        for k, a_dict in self.articles_objs.items():
            loaded_flag = " Loaded " if (a_dict['body_lines'] is not None) else "Unloaded"
            print(f"{k.ljust(8)} ({loaded_flag}): {a_dict['article_title']}")


crr = CRR()
