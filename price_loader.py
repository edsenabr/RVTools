#!/usr/bin/python3
import math
from operator import itemgetter
import requests
import re
from bs4 import BeautifulSoup
from queue import Queue
from threading import Thread
import argparse
from tqdm import tqdm
from timebudget import timebudget
timebudget.set_quiet()  # don't show measurements as they happen

windows = re.compile('.*windows.*', re.IGNORECASE)
sles = re.compile('.*SUSE.*', re.IGNORECASE)
rhel = re.compile('.*Red Hat.*', re.IGNORECASE)
free = re.compile('.*((debian)|(centos)|(coreos)|(ubuntu)).*', re.IGNORECASE)


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
    "southamerica-west1": "sant",
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

base_price = [
	"e2_predefined",
	"e2_custommachinetypepricing",
	"n2_predefined",
	"n2_custommachinetypepricing",
	"n2d_machine_types",
	"n2d_custommachinetypepricing",
	"t2d_machine_types",
	"n1_predefined",
	"n1_custommachinetypepricing",
	"c2_machine_types",
	"a2-base-price",
    "c2d_vcpus_and_memory",
]

ignored_frames = [
    "n1_extendedmemory",
	"n2_extendedmemory",
	"n2d_extendedmemory",
	"n2_n2d_c2",
	"c2d",
	"combining_commitments_with_reservations",
    "localssdpricing"
]

ignored_families = [
    'g1', 'f1'
]
shared_types = [
    'e2-micro', 'e2-small', 'e2-medium'
]

NUM_FETCH_THREADS = 50


predefined_names = re.compile('^\w{2,3}-.+?(-\d{1,3})?$', re.IGNORECASE)
base_name = re.compile('^(.+) (.+)$')


class Incrementor:
	def __init__(self, value):
		self.value = value
	def pre(self, mu=1):
		self.value += mu
		return self.value
	def post(self, mu=1):
		current = self.value
		self.value += mu
		return current
	def __str__(self):
		return str(self.value)

class Frame:
    def __init__(self, id: str, src: str):
        self.id = id
        self.src = src
        self.price_list = None
        self.raw_data = None

    @timebudget
    def frame_get(self):
        with timebudget("load_frame", quiet=True):
            self.raw_data = BeautifulSoup(
                requests.get('https://cloud.google.com%s' % self.src).text, 
                'html.parser'
            ).find('table').find('tbody').find_all('tr')
        if self.id == 've1-standard-72':
            self.load_gcve_prices()
        elif self.id =='persistentdisk':
            self.load_disk_prices()
        elif self.is_base():
            self.load_custom_prices()
        else:
            self.load_predefined_prices()

    def is_base(self):
        return self.id in base_price

    @timebudget
    def load_disk_prices(self):

        for row in self.raw_data:
            if (row.td is None):
                continue
            name = row.td.text.strip()
            base_re = re.compile('^(.+?) provisioned space$')
            definition = base_re.search(name)
            if (not definition):
                continue

            name = definition.group(1).lower()
            if name is None:
                continue

            for region in self.regions:
                od = parse_number(row, 2, region, self.period)
                if (not od is None):
                    self.price_list.lists['disk'].append({
                        "name": name,
                        "region": region,
                        "price": parse_number(row, 2, region, self.period)
                    })


    @timebudget
    def load_gcve_prices(self):
        for row in self.raw_data:
            if (row.td is None):
                continue
            name = cleanup_name(row.td.text)
            if (name != 've1-standard-72'):
                continue

            for region in self.regions:
                od = parse_number(row, 2, region, 'hourly')
                if (od is None):
                    continue

                self.price_list.lists["predefined"].append({
                    "family": "ve1",
                    "name": name,
                    "cpus": 72,
                    "memory": 768,
                    "region": region,
                    "od": od * 730,
                    "spot": None,
                    "cud1y": parse_number(row.select_one('td:nth-of-type(2)'), 1, region, 'hourly') * 730,
                    "cud3y": parse_number(row.select_one('td:nth-of-type(2)'), 2, region, 'hourly') * 730
                })

    # https://cloud.google.com/compute/docs/machine-types#machine_type_comparison
    # Machine series	            vCPUs	Memory (per vCPU)
    # E2 General-purpose            2–32	0.5–8 GB
    # N1 General-purpose	        1–96	0.9–6.5 GB
    # N2 General-purpose	        2–128	0.5–8 GB
    # N2D General-purpose	        2–224	0.5–8 GB

    cpu_ratio= {
        "e2":  {"cpu_min": 2, "cpu_max": 32, "memory_min": 0.5, "memory_max": 8  },
        "n1":  {"cpu_min": 1, "cpu_max": 96, "memory_min": 0.9, "memory_max": 6.5},
        "n2":  {"cpu_min": 2, "cpu_max": 128,"memory_min": 0.5, "memory_max": 8  },
        "n2d": {"cpu_min": 2, "cpu_max": 224,"memory_min": 0.5, "memory_max": 8  }
    }

    @timebudget
    def load_custom_prices(self):
        custom = None
        match = re.match("^([a-z0-9]{2,3})(_|-).+$",self.id)
        family_name = match.group(1) if match else None
        if family_name in ignored_families:
            return

        for region in self.regions:

            parsed_data = { 
                "name": family_name,
                "region":region
            }

            if family_name in self.cpu_ratio.keys():
                parsed_data.update(self.cpu_ratio[family_name])

            for row in self.raw_data:
                if (row.td is None):
                    continue

                name = row.td.text.strip()


                if (is_predefined(name)):
                    continue

                [custom, unit] = parse_base_price_name(name)

                # print("%s|%s|%s|%s" % (family_name, name, unit, self.id))
                if unit is None:
                    continue
            
                od = parse_number(row, 2, region, self.period)
                if od is None:
                    continue
                parsed_data.update({
                    # apparently, the montly pricing page already has SUD applied
                    #"{unit}_od".format(unit=unit): od * 0.8 if family_name in ['n2', 'n2d', 'c2', 'c2d', 'm1', 'm2'] else od,
                    "{unit}_od".format(unit=unit): od,
                    "{unit}_spot".format(unit=unit): parse_number(row, 3, region, self.period),
                    "{unit}_cud1y".format(unit=unit): parse_number(row, 4, region, self.period),
                    "{unit}_cud3y".format(unit=unit): parse_number(row, 5, region, self.period)
                })
            if "vcpus_od" in parsed_data  and "memory_od" in parsed_data:
                if custom:
                    self.price_list.lists['custom'].append(parsed_data)
                else:
                    self.price_list.lists['standard'].append(parsed_data)
            else:
                pass

    @timebudget
    def load_predefined_prices(self):
        for row in self.raw_data:
            if (row.td is None):
                continue

            
            name = cleanup_name(row.td.text)
            if (not is_predefined(name)):
                continue

            if name in shared_types:
                continue

            match = re.match("^([a-z0-9]{2,3})(_|-).+$",name)
            family_name = match.group(1) if match else None
            if family_name in ignored_families:
                return
            
            cpu = parse_number(row, 2)
            memory = parse_number(row, 3)

            for region in self.regions:
                od = parse_number(row, 4, region, self.period)
                if (not od is None):
                    self.price_list.lists['predefined'].append({
                        "family": family_name,
                        "name": name,
                        "cpus": cpu,
                        "memory": memory,
                        "region": region,
                        # apparently, the montly pricing page already has SUD applied
                        #"od": od * 0.8 if family_name in ['n2', 'n2d', 'c2', 'c2d', 'm1', 'm2'] else od,
                        "od": od,
                        "spot": parse_number(row, 5, region, self.period),
                        "cud1y": parse_number(row, 6, region, self.period),
                        "cud3y": parse_number(row, 7, region, self.period)
                    })


class PriceList:
    def __init__(self, regions, period):
        self.frame_queue = Queue()
        self.regions = regions
        self.period = period

        self.lists = { 
            'disk': [],
            'predefined': [],
            'standard': [],
            'custom': [],
            'predefined_bycud': []
        }
        
        self.load_initial_data()
        self.load_frames()
        self.fill_empty_prices()

    def count(self):
        return "loaded {predefined} standard types, {custom} custom types, {disk} disk prices and {os} O.S. prices.".format(
            predefined=len(self.lists['predefined']),
            custom=len(self.lists['custom']),
            disk=len(self.lists['disk']),
            os=len(self.images)
        )

    def find_id(self, frame):
        return [sibling['id'] for sibling in frame.parent.find_previous_siblings() if (
            sibling.name in ['h3', 'h4'] and 
            sibling['id'] not in ignored_frames
        )][0]

    def test_and_add(self, frame):
        id = self.find_id(frame)
        if not id is None: 
            self.add_frame(Frame(id,frame.get('src')))
    
    @timebudget     
    def list_frames(self, url):
        with timebudget("list_frames::get"):
            html_text = requests.get(url).text
        with timebudget("list_frames::parse"):
            soup = BeautifulSoup(html_text, 'html.parser')
        frames = soup.find_all('iframe')
        [self.test_and_add(frame) for frame in [frame for frame in frames]]
        return soup


    @timebudget
    def load_initial_data(self):
        self.list_frames('https://cloud.google.com/compute/vm-instance-pricing')
        soup = self.list_frames('https://cloud.google.com/compute/disks-image-pricing')
        self.images = self.parse_premium_images(soup)

        html_text = requests.get('https://cloud.google.com/vmware-engine/pricing').text
        soup = BeautifulSoup(html_text, 'html.parser')
        self.add_frame(Frame('ve1-standard-72',soup.find('iframe').get('src')))

    def add_frame(self, frame: Frame) -> None:
        frame.price_list = self
        frame.regions = self.regions
        frame.period = self.period
        self.frame_queue.put(frame)

    @timebudget
    def load_frames(self) -> None:
        with tqdm(total=self.frame_queue.qsize(), desc="loading price list") as self.progress_bar:
            for i in range(NUM_FETCH_THREADS):
                Thread(target=self.process_frame_queue, daemon=True).start()
            self.frame_queue.join()

    def process_frame_queue(self) -> None:
        while True:
            self.frame_queue.get().frame_get()
            self.frame_queue.task_done()
            self.progress_bar.update()


    def fill_empty_price(self, item) -> None:
        family_price = [standard for standard in self.lists['standard'] if (
            standard["region"] == item["region"] and 
            standard["name"] == item["family"]
        )][0]
        item["cud1y"] = (item["cpus"]*family_price["vcpus_cud1y"])+(item["memory"]*family_price["memory_cud1y"])
        item["cud3y"] = (item["cpus"]*family_price["vcpus_cud3y"])+(item["memory"]*family_price["memory_cud3y"])
        return item

    def fill_empty_prices(self) -> None:
        self.lists['predefined'] = [
            predefined 
                if not predefined['cud1y'] is None 
                else self.fill_empty_price(predefined) 
            for predefined in self.lists['predefined'] 
        ]

    def parse_premium_images(self, soup) -> dict:
        cleanup = re.compile('[^0-9\.]+')
        prices = {}
        #rhel =< 4vcpus <strong>$0.06 USD/hour</strong>
        try:
            prices['rhel_less_equal_4vcpus'] = float(cleanup.sub("", soup.find('h3', {"id": "rhel_images"}).find_next_sibling('p').select_one('li:nth-of-type(1)').find('strong').text)) * 730 
        except Exception as e:
            print("Failed to load rhel_less_equal_4vcpus: %s" % e)
            pass

        try:
            prices['rhel_more_4vcpus'] = float(cleanup.sub("", soup.find('h3', {"id": "rhel_images"}).find_next_sibling('p').select_one('li:nth-of-type(2)').find('strong').text)) * 730 
        except Exception as e:
            print("Failed to load rhel_more_4vcpus: %s" % e)
            pass

        try:
            prices['sles'] = float(cleanup.sub("", soup.find('h3', {"id": "suse_images"}).find_next_sibling('p').select_one('li:nth-of-type(2)').find('strong').text)) * 730 
        except Exception as e:
            print("Failed to load sles: %s" % e)
            pass

        try:
            prices['windows_per_core'] =float(re.search('\$([0-9\.]+) USD per core/hour for all other machine types', soup.find('h3', {"id": "windows_server_pricing"}).find_next('ul').select_one('li:nth-of-type(1)').text).group(1)) * 730 
        except  Exception as e:
            print("Failed to load windows_per_core: %s" % e)
            pass

        return prices

    @timebudget
    def select_price(self, commit, cpus, memory, region, verbose=False):
        cpu = math.ceil(cpus)
        mem = math.ceil(memory/1024)

        if verbose:
            print('commit:\t\t`{commit}`'.format(commit=commit))
        predefined = self.get_predefined_type(commit, region, cpu, mem)
        custom_family = self.get_custom_family(region, cpu, mem, True)
        if not custom_family is None:
            if verbose:
                print('predefined:\t`{name}` costs ${price}'.format(name=predefined['name'], price=predefined[commit]))
                print('custom:\t\t`{name}` costs ${price}'.format(name=custom_family['name'], price=custom_family[commit]))
            if custom_family[commit] < predefined[commit]:
                if verbose:
                    print('cheaper:\tcustom\n')
                    return custom_family
            elif verbose:
                    print('cheaper:\tpredefined\n')
        elif verbose:
            print('custom:\t\tnone found; too big?\n')
        return predefined


    def select_disk_price(self, name, region) -> float:
        return [disk["price"] for disk in self.lists['disk'] if (
            disk["region"] == region and 
            disk["name"]==name
        )][0]

    def get_cpu(self, custom, cpu):
        return int(max(cpu, custom["cpu_min"]))

    def get_memory(self, custom, cpu, mem):
        return int(max(mem, math.ceil(self.get_cpu(custom, cpu)*custom['memory_min'])))

    @timebudget
    def get_custom_families(self, region:str, cpu:int, mem:int, cud:bool=False) -> dict:
        return sorted(
            [{
                "family": custom['name'],
                'name': "%s-custom-%s-%s" % (custom['name'], self.get_cpu(custom, cpu), self.get_memory(custom, cpu, mem)), 
                "cpus": self.get_cpu(custom, cpu),
                "memory": self.get_memory(custom, cpu, mem),
                "region": region,
                'spot': custom["vcpus_spot"]*self.get_cpu(custom, cpu) + custom["memory_spot"]*self.get_memory(custom, cpu, mem), 
                'od': round((custom["vcpus_od"]*self.get_cpu(custom, cpu) + custom["memory_od"]*self.get_memory(custom, cpu, mem)),2), 
                'cud1y': round((custom["vcpus_cud1y"]*self.get_cpu(custom, cpu) + custom["memory_cud1y"]*self.get_memory(custom, cpu, mem)),2), 
                'cud3y': round((custom["vcpus_cud3y"]*self.get_cpu(custom, cpu) + custom["memory_cud3y"]*self.get_memory(custom, cpu, mem)),2)
            } for custom in self.lists['custom'] if (
                custom["region"] == region and 
                custom["cpu_max"] >= self.get_cpu(custom, cpu) and 
                custom["memory_max"] >= self.get_memory(custom, cpu, mem) / self.get_cpu(custom, cpu)
            )],
            key=itemgetter('cud1y' if cud else 'od')
        )

    def get_custom_family(self, region:str, cpu:int, mem:int, cud:bool=False) -> dict:
        custom = self.get_custom_families(region, cpu, mem, cud)
        return None if len(custom) == 0 else custom[0]

    @timebudget
    def get_predefined_type(self, commit:str, region:str, cpu:int, mem:int):
        return [predefined for predefined in sorted(
            self.lists['predefined'],
            key=itemgetter('od')
        ) if (
            predefined["region"] == region and 
            predefined["cpus"] >= cpu and 
            predefined["memory"] >= mem
        )][0]

    def get_gcve_price(self, region:str):
        price = [predefined for predefined in self.lists['predefined'] if (
            predefined["region"] == region and 
            predefined["name"] == "ve1-standard-72"
        )]
        return None if len(price) == 0 else price[0]


    def get_os_price(self, os, cpus): 
        if windows.match(os):
            return self.images['windows_per_core'] * cpus
        elif sles.match(os):
            return self.images['sles']
        elif rhel.match(os):
            return self.images['rhel_less_equal_4vcpus'] if cpus <= 4 else self.images['rhel_more_4vcpus']
        elif free.match(os):
            return 0

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

def is_predefined(name:str): 
    return predefined_names.match(name)

def parse_base_price_name(name:str):
    definition = base_name.search(name)
    return [
        definition.group(1).lower() == "custom",
        definition.group(2).lower()
    ]

def get_parser(h):
    parser = argparse.ArgumentParser(add_help=h)
    parser.add_argument("-t", "--threads", help="regions to be loaded", required=False)
    parser.add_argument("-r", "--regions", nargs='*', help="regions to be loaded", required=True)
    return parser

if (__name__=="__main__"):
    timebudget.set_quiet()  # don't show measurements as they happen
    timebudget.report_at_exit()  # Generate report when the program exits
    p = get_parser(h=True)
    args = p.parse_args()
    if not args.threads is None:
        NUM_FETCH_THREADS=args.threads
        print("running with %s threads" % NUM_FETCH_THREADS)

    price_list = PriceList(args.regions, 'monthly')
    pass