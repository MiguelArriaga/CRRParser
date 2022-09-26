import os
import json
import requests
import unicodedata
import base64
import hashlib
from bs4 import BeautifulSoup


def save_json(obj, path):
    with open(path, "w") as fp:
        json.dump(obj, fp)


def load_json(path):
    with open(path, "r") as fp:
        obj = json.load(fp)
    return obj


def clean_node(txt):
    return unicodedata.normalize("NFKD", txt.text.replace("\n", " ").strip())


TEMP_DIR = "C:/Temp/CRR_parser"
os.makedirs(TEMP_DIR, exist_ok=True)
IMG_DIR = os.path.join(TEMP_DIR, "Images")
os.makedirs(IMG_DIR, exist_ok=True)

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
            self.articles = self.load_index()

        self.always_save = always_save
        if self.always_save:
            self.save("Initial CRR Saving.")

    @classmethod
    def get_article_dict(cls, a_object, base_url=EBA_WEBSITE):
        artic_dict = {}
        text = unicodedata.normalize("NFKD", a_object.text.strip())
        artic_dict['text'] = text
        artic_dict['url'] = base_url + a_object["href"]
        artic_dict['article_num'] = text.split(":")[0].replace("Article", "").strip()
        artic_dict['article_title'] = text.split(":")[1].strip()
        artic_dict['full_html'] = None
        artic_dict['body_lines'] = None
        artic_dict['article_structure'] = None
        return artic_dict

    @classmethod
    def parse_article_points(cls, article_points_raw, footnotes=False):
        full_article = {}
        for a_point in [p for p in article_points_raw if (p.get("id", "") != "footnotes") or footnotes]:
            paragraphs = a_point.findChildren(recursive=False)
            if len(paragraphs) == 2:
                point = clean_node(paragraphs[0])
                ps = paragraphs[1].findChildren(recursive=False)
                if len(ps) == 0:
                    paragraphs = [paragraphs[1]]
                else:
                    paragraphs = ps
            elif a_point.name == 'p':
                paragraphs = full_article[point] + [a_point]
            else:
                raise ValueError("Parsing Error with article points")
            full_article[point] = paragraphs
        return full_article

    @classmethod
    def parse_table_elem(cls, elem):
        p_rows = []
        for row in elem.findChildren("tr"):
            cells = [[cls.parse_elem(p) for p in c.findChildren("p")] for c in row.findChildren("td")]
            p_rows.append({cells[0][0] + cells[1][0]: cells[2]})
        return p_rows

    @classmethod
    def parse_elem(cls, elem):
        ucls = lambda x: x in elem.attrs.get('class', [])
        gcls = lambda x: any([x in clss for clss in elem.attrs.get('class', [])])

        output = None

        if isinstance(elem, str):
            output = elem.strip()

        elif elem.name == 'p':
            if gcls("container"):
                output = [cls.parse_elem(e) for e in elem.contents]
            else:
                output = elem.text.strip()

        elif ucls('inline-element'):
            output = [cls.parse_elem(e) for e in elem.contents]

        elif ucls('list'):
            output = [cls.parse_elem(e) for e in elem.contents]

        elif elem.name == 'table':
            output = cls.parse_table_elem(elem)

        elif elem.name == 'div':
            children = elem.findChildren(recursive=False)
            parsed_children = [cls.parse_elem(c) for c in children[1].findChildren(recursive=False)]
            if len(parsed_children) == 1:
                parsed_children = parsed_children[0]
            output = {children[0].text.strip():parsed_children}

        elif elem.name == "img":
            img_data = elem.attrs['src'].split(',')[1]
            img_name = hashlib.md5(img_data.encode()).hexdigest() + ".jpg"
            print("saving image "+img_name)
            img_path = os.path.join(IMG_DIR, img_name)
            with open(img_path, 'wb') as jpg:
                jpg.write(base64.b64decode(img_data))
            output = {"img_name": img_name, 'width': elem.attrs['width'], 'height': elem.attrs['height']}

        else:
            raise ValueError(f"don't know {elem.name}")

        if isinstance(output, list) and len(output) == 1:
            output = output[0]

        return output

    def get_article_body(cls, article_dict, footnotes=False):

        if article_dict['body_lines'] is None:

            # Get HTML of article online if we don't have it yet
            if article_dict['full_html'] is None:
                print(f"Getting Article {article_dict['article_num']} online")
                article_dict['full_html'] = requests.get(article_dict['url']).text

            # Parse HTML (with BeautifulSoup) to find the "Main Content:" part
            article_soup = BeautifulSoup(article_dict['full_html'], 'html.parser')
            main_content_soup = (article_soup
                .find(lambda tag: tag.name == "div" and tag.text.startswith("Main content:"))
                .parent.findChildren("div", recursive=False)[1]
                .findChildren(recursive=False)[0]
                )

            # Get each article point as a key-value dict (fixing some CRR inconsistencies)
            article_points_raw = main_content_soup.findChildren(recursive=False)
            article_points = cls.parse_article_points(article_points_raw, footnotes=footnotes)

            # Build full article structure
            article_structure = {pt: [
                cls.parse_elem(elem) for elem in elems]
                for pt, elems in article_points.items()}
            article_dict['article_structure'] = article_structure

            # Preliminary approach simply uses the article_points_raw. It is potentially more robust
            article_dict['body_lines'] = [unicodedata.normalize("NFKD", line.text.replace("\n", " ")) for line in
                                          article_points_raw if (line.get("id", "") != "footnotes") or footnotes]
        return article_dict['body_lines']

    def load_index(self):
        html_text = requests.get(CRR_HOMEPAGE).text
        soup = BeautifulSoup(html_text, 'html.parser')
        all_article_objects = soup.find_all("a", attrs={"text-type": "Article"})
        articles = {}
        for article in all_article_objects:
            a = self.get_article_dict(article)
            articles[a['article_num']] = a
        return articles

    def save(self, msg="Saving"):
        if msg: print(msg)
        save_json(self.__dict__, self.crr_index_path)

    def __getitem__(self, item):
        article = self.articles.get(str(item))
        if article is None:
            raise ValueError("Could not find article. Use crr.list_articles() for full list of articles.")
        a = self.get_article_body(article, footnotes=False)
        if self.always_save:
            self.save()
        return a

    def list_articles(self):
        for k, a_dict in self.articles.items():
            loaded_flag = " Loaded " if (a_dict['body_lines'] is not None) else "Unloaded"
            print(f"{k.ljust(8)} ({loaded_flag}): {a_dict['article_title']}")


crr = CRR(load_cached=False, always_save=False)

crr[153]
crr.save()
