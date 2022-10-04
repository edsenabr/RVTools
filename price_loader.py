#!/usr/bin/python3
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import re
from operator import itemgetter
from time import time

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from frame import Frame

from opentelemetry.trace import get_tracer, get_current_span
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider


windows = re.compile('.*windows.*', re.IGNORECASE)
sles = re.compile('.*SUSE.*', re.IGNORECASE)
rhel = re.compile('.*Red Hat.*', re.IGNORECASE)
free = re.compile('.*((debian)|(centos)|(coreos)|(ubuntu)).*', re.IGNORECASE)

NUM_FETCH_THREADS = 100


class PriceList:
    def __init__(self, regions, period, *ignore_cache):
        self.regions = regions
        self.period = period
        self.ignore_cache = ignore_cache

        self.lists = { 
            'disk': [],
            'predefined': [],
            'standard': [],
            'custom': [],
            'predefined_bycud': [],
            "images" : {}
        }

        with get_tracer("price_loader").start_as_current_span("load_price_data"):
            with tqdm(total=0, desc="Loading price data") as self.progress_bar:
                with ThreadPoolExecutor(max_workers=NUM_FETCH_THREADS) as self.frameExecutor:
                    self.load_from_cache() or self.load_initial_data()


    def count(self):
        return "loaded {predefined} standard types, {custom} custom types, {disk} disk prices and {os} O.S. prices.".format(
            predefined=len(self.lists['predefined']),
            custom=len(self.lists['custom']),
            disk=len(self.lists['disk']),
            os=len(self.lists["images"])
        )

    def list_frames(self, url, span=None):
        ctx = set_span_in_context(span)
        with get_tracer("price_loader").start_as_current_span("list_frames", context=ctx, attributes={'url':url}):
            with get_tracer("price_loader").start_as_current_span("main_page"):
                html_text = requests.get(url).text
            with get_tracer("price_loader").start_as_current_span("parse"):
                soup = BeautifulSoup(html_text, 'html.parser')
                frames = soup.find_all('iframe')
            with get_tracer("price_loader").start_as_current_span("load_frames"):
                [self.add_frame(Frame.from_soup(frame)) for frame in [frame for frame in frames]]
            return soup

    def load_gcve_data(self, span):
        ctx = set_span_in_context(span)
        with get_tracer("price_loader").start_as_current_span("load_gcve_data", context=ctx):
            html_text = requests.get('https://cloud.google.com/vmware-engine/pricing').text
            soup = BeautifulSoup(html_text, 'html.parser')
            self.add_frame(Frame('ve1-standard-72',soup.find('iframe').get('src')))

    def load_from_cache(self):
        if self.ignore_cache:
            return False

        try:
            with open('price_loader.json') as cache:
                data = json.load(cache)
                if not all(region in data['regions'] for region in self.regions):
                    return False
                self.lists = data["lists"]
                self.last_update = data["last_update"]
                self.regions = data['regions']
                return True
        except FileNotFoundError:
            return False

    def load_initial_data(self):
        with get_tracer("price_loader").start_as_current_span("load_initial_data"):
            with ThreadPoolExecutor(max_workers=10) as executor:
                # executor.submit(self.list_frames, 'https://cloud.google.com/compute/vm-instance-pricing', get_current_span())
                executor.submit(self.list_prices, get_current_span())
                # executor.submit(self.parse_premium_images, get_current_span())
                executor.submit(self.load_gcve_data, get_current_span())
            self.frameExecutor.shutdown()
        self.last_update = time()
        self.fill_empty_prices()
        self.save_cache()
            
    def save_cache(self):
        with open('price_loader.json', 'w') as cache:
            json.dump(
                {
                    "last_update" : self.last_update,
                    "regions" : self.regions,
                    "lists": self.lists
                }, 
                cache
            )

    def list_prices(self, span):
        ctx = set_span_in_context(span)
        with get_tracer("price_loader").start_as_current_span("load prices", context=ctx):
            soup = self.list_frames('https://cloud.google.com/compute/all-pricing', get_current_span())
            self.parse_premium_images(span, soup)

    def add_frame(self, frame: Frame) -> None:
        if Frame is None:
            return
        frame.price_list = self
        frame.regions = self.regions
        frame.period = self.period
        frame.parent_span = get_current_span()
        self.frameExecutor.submit(frame.frame_get)
        self.progress_bar.total += 1
        self.progress_bar.refresh()

    def fill_empty_price(self, item) -> None:
        family_price = [standard for standard in self.lists['standard'] if (
            standard["region"] == item["region"] and 
            standard["name"] == item["family"]
        )][0]
        item["cud1y"] = (item["cpus"]*family_price["vcpus_cud1y"])+(item["memory"]*family_price["memory_cud1y"])
        item["cud3y"] = (item["cpus"]*family_price["vcpus_cud3y"])+(item["memory"]*family_price["memory_cud3y"])
        return item

    def fill_empty_prices(self) -> None:
        with get_tracer("price_loader").start_as_current_span("fill_empty_prices"):
            self.lists['predefined'] = [
                predefined 
                    if not predefined['cud1y'] is None 
                    else self.fill_empty_price(predefined) 
                for predefined in self.lists['predefined'] 
            ]

    def parse_premium_images(self, span, soup=None) -> dict:
        ctx = set_span_in_context(span)
        with get_tracer("price_loader").start_as_current_span("parse_premium_images", context=ctx):
            if soup is None:
                soup = self.list_frames('https://cloud.google.com/compute/disks-image-pricing', get_current_span())
            #soup = self.list_frames('https://cloud.google.com/compute/all-pricing', get_current_span())
            cleanup = re.compile('[^0-9\.]+')
            #rhel =< 4vcpus <strong>$0.06 USD/hour</strong>
            try:
                self.lists["images"]['rhel_less_equal_4vcpus'] = float(cleanup.sub("", soup.find('h3', {"id": "rhel_images"}).find_next_sibling('p').select_one('li:nth-of-type(1)').find('strong').text)) * 730 
            except Exception as e:
                print("Failed to load rhel_less_equal_4vcpus: %s" % e)
                pass

            try:
                self.lists["images"]['rhel_more_4vcpus'] = float(cleanup.sub("", soup.find('h3', {"id": "rhel_images"}).find_next_sibling('p').select_one('li:nth-of-type(2)').find('strong').text)) * 730 
            except Exception as e:
                print("Failed to load rhel_more_4vcpus: %s" % e)
                pass

            try:
                self.lists["images"]['sles'] = float(cleanup.sub("", soup.find('h3', {"id": "suse_images"}).find_next_sibling('p').select_one('li:nth-of-type(2)').find('strong').text)) * 730 
            except Exception as e:
                print("Failed to load sles: %s" % e)
                pass

            try:
                self.lists["images"]['windows_per_core'] =float(re.search('\$([0-9\.]+) USD per core/hour for all other machine types', soup.find('h3', {"id": "windows_server_pricing"}).find_next('ul').select_one('li:nth-of-type(1)').text).group(1)) * 730 
            except  Exception as e:
                print("Failed to load windows_per_core: %s" % e)
                pass


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
            return self.lists["images"]['windows_per_core'] * cpus
        elif sles.match(os):
            return self.lists["images"]['sles']
        elif rhel.match(os):
            return self.lists["images"]['rhel_less_equal_4vcpus'] if cpus <= 4 else self.lists["images"]['rhel_more_4vcpus']
        elif free.match(os):
            return 0



def get_parser(h):
    parser = argparse.ArgumentParser(add_help=h)
    parser.add_argument("-t", "--threads", help="regions to be loaded", required=False)
    parser.add_argument("-r", "--regions", nargs='*', help="regions to be loaded", required=True)
    parser.add_argument("-nc", "--nocache", action='store_true', help="ignore cache")
    return parser

if (__name__=="__main__"):
    p = get_parser(h=True)
    args = p.parse_args()
    if not args.threads is None:
        NUM_FETCH_THREADS=int(args.threads)
        print("running with %s threads" % NUM_FETCH_THREADS)

    price_list = PriceList(args.regions, 'monthly', args.nocache)
    pass
