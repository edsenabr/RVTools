import requests
from bs4 import BeautifulSoup
import re 

region_codes = {
    "us-central1": "io",
    "us-west1": "ore",
    "us-west2": "la",
    "us-west3": "slc",
    "us-west4": "lv",
    "us-east4": "nv",
    "us-east1": "sc",
    "northamerica-northeast1": "mtreal",
    "northamerica-northeast2": "tor",
    "southamerica-east1": "spaulo",
    "southamerica-west1": "san",
    "europe-west1": "eu",
    "europe-north1": "fi",
    "europe-west3": "ffurt",
    "europe-west2": "lon",
    "europe-west4": "nether",
    "europe-west6": "zur",
    "europe-west8": "ml",
    "europe-central2": "wsaw",
    "asia-south1": "mbai",
    "asia-south2": "del",
    "asia-southeast1": "sg",
    "asia-southeast2": "jk",
    "australia-southeast1": "syd",
    "australia-southeast2": "mel",
    "asia-east2": "hk",
    "asia-east1": "tw",
    "asia-northeast1": "ja",
    "asia-northeast2": "osa",
    "asia-northeast3": "kr"
}


class GCVEFrame:
    def __init__(self) -> None:
        self.name = "predefined"
        html_text = requests.get('https://cloud.google.com/vmware-engine/pricing').text
        soup = BeautifulSoup(html_text, 'html.parser')
        text = requests.get(soup.find('iframe').get('src')).text
        soup = BeautifulSoup(text, 'html.parser')
        self.raw_data = soup.find('table').find('tbody').find_all('tr')

    def parse(self, regions) -> list:
        parsed_data = []
        for row in self.raw_data:
            if (row.td is None):
                continue
            name = cleanup_name(row.td.text)
            if (name != 've1-standard-72'):
                continue

            for region in regions:
                od = parse_number(row, 2, region, 'hourly')
                if (od is None):
                    print (f"Failed to load GCVE on-demand price for {region}")
                    continue

                parsed_data.append({
                    "family": "ve1",
                    "name": name,
                    "cpus": 72,
                    "memory": 768,
                    "region": region,
                    "od": od * 730,
                    "spot": None,
                    "cud1y": parse_number(row.select_one('td:nth-of-type(2)'), 1, region, 'hourly') * 730,
                    "cud3y": parse_number(row.select_one('td:nth-of-type(2)'), 3, region, 'hourly') * 730
                })
            return parsed_data


def cleanup_name(name):
    name = name.strip()
    skylake = re.compile('Skylake Platform only', re.IGNORECASE)
    name = skylake.sub('', name)
    return name

def parse_number(row, index, region=None, period=None):
    cleanup = re.compile('[^0-9\.]+')
    column = row.select_one('td:nth-of-type(%s)' % index)
    number = None
    if not column is None:
        text = ""
        if not period is None:
            try:
                text = column.attrs['%s-%s' % (region_codes[region], period)].strip()
            except:
                pass
        else: 
            text = column.text.strip() or column.attrs['default'].strip()
        text = cleanup.sub("", text)
        if text:    
            number = float(text)
    return number
