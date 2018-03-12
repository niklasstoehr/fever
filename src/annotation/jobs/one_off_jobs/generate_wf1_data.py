

from botocore.exceptions import ClientError
from tqdm import tqdm

from dataset.jobs.test3 import untokenize
from persistence.s3_persistence import S3Writer

import json


data_folder = "data"
page_titles = "pages.txt"
redirects_file = "redirect.txt"

import os


def clean(filename):
    return filename.replace("(", "-LRB-").replace(")", "-RRB-").replace("[", "-LSB-") \
        .replace("]", "-RSB-").replace(":", "-COLON-").replace(" ", "_")


def get_first_line(name):
    name = name.split("#")[0]
    if len(name) == 0:
        return None
    obj = get_wiki_entry(name)

    if obj is None:
        return obj

    intro = obj["text"].split("\n")
    return obj["canonical_entity"], intro[0].split("\t")[1]


def get_redirects():
    redirs = os.path.join(data_folder, redirects_file)
    rd = dict()
    with open(redirs, "r") as f:
        while True:
            line = f.readline()
            if line == "":
                break

            bits = line.strip().split("\t")
            if len(bits) == 2:
                frm, to = bits
                rd[frm] = to

    return rd


def recursive_redirect_lookup(redirects, word):
    if word in redirects:
        try:
            return recursive_redirect_lookup(redirects, redirects[word])
        except RecursionError:
            return word
    else:
        return word


def get_wiki_entry(name):
    s3 = S3Writer("com.amazon.evi.fever.wiki")
    try:
        key = s3.clean("intro/"+name)

        return {"text":s3.read_string(key), "canonical_entity":name}
    except:
        try:
            if name[0].islower():
                return get_wiki_entry(name[0].upper()+name[1:])
            else:
                return get_wiki_entry(recursive_redirect_lookup(redirects,redirects[name]))
        except:
            return None


redirects = get_redirects()

pages_file = os.path.join(data_folder, page_titles)

pages = []
with open(pages_file, "r")  as f:
    pages.extend([line.strip() for line in f.readlines()])

s3 = S3Writer("com.amazon.evi.fever.wiki")

global_id = 0
extra_pages = set()

with open("extra_pages.txt", "r")  as f:
    extra_pages.update([line.strip() for line in f.readlines()])


done_pages = set()

live = []
if os.path.exists("data/live.json"):
    with open("data/live.json","r") as f:
        live = json.load(f)

for item in tqdm(live,desc="Loading existing claims"):
    global_id+=1
    entity = item["entity"]
    if entity not in done_pages:
        done_pages.add(entity)


def add_page(page,global_id):
    try:
        print("Look up ", page)
        entry = get_wiki_entry(page)
        if entry is None:
            return
        body = entry["text"]

        intro = body.split("\n")

        for idx, line in tqdm(enumerate(intro), desc=page):
            bits = line.split("\t")

            id = bits[0]

            if len(bits) > 1:
                context_before = ""
                context_after = ""

                if idx > 0:
                    prev = intro[idx - 1]
                    prev_split = prev.split("\t")
                    if len(prev) > 1:
                        context_before = untokenize(prev_split[1])

                if idx < len(intro) - 1:
                    prev = intro[idx + 1]
                    prev_split = prev.split("\t")
                    if len(prev) > 1:
                        context_after = untokenize(prev_split[1])

                sentence = untokenize(bits[1])
                dictionary = dict()

                if len(bits) > 3:
                    links = bits[3::2]

                    for link in tqdm(links, desc=id):

                        try:
                            result = get_first_line(link)
                            if result is not None:
                                entity_name, first_line = result
                                dictionary[entity_name] = untokenize(first_line)
                                extra_pages.add(entity_name)
                            else:
                                print("Could not find " + link)

                        except Exception as e:
                            print("Dict err")
                            print(e)

                            pass

                live.append({"id": global_id, "sentence_id": bits[0], "entity": page, "sentence": sentence,
                                "dictionary": dictionary, "context_before": context_before,
                                "context_after": context_after})


    except ClientError as e:
        pass



for page in tqdm(pages):
    if page not in done_pages:
        add_page(page,global_id)
        global_id += 1

        with open('data/live.json', 'w+') as outfile:
            json.dump(live, outfile)

        with open('data/extra_pages.txt', 'w+') as outfile:
            outfile.write("\n".join(list(extra_pages)))