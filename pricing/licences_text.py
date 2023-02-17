import re
cleanup = re.compile('[^0-9\.]+')

class Licences:
    def __init__(self, soup, period) -> None:
        self.name = "images"
        self.soup = soup
        self.period = period

    def parse(self) -> list:
        multiplier = 730 if self.period == "monthly" else 1
        parsed_data = {}
        try:

            parsed_data['rhel_less_equal_4vcpus'] = float(
                cleanup.sub("", 
                    self.soup.find('h3', {"id": "rhel_images"})
                        .find_next_sibling('p')
                        .select_one('li:nth-of-type(1)')
                        .find('strong')
                        .text
                )
            ) * multiplier
        except Exception as e:
            print("Failed to load rhel_less_equal_4vcpus: %s" % e)
            pass

        try:
            parsed_data['rhel_more_4vcpus'] = float(
                cleanup.sub("", 
                    self.soup.find('h3', {"id": "rhel_images"})
                    .find_next_sibling('p')
                    .select_one('li:nth-of-type(2)')
                    .find('strong')
                    .text
                )
            ) * multiplier
        except Exception as e:
            print("Failed to load rhel_more_4vcpus: %s" % e)
            pass

        try:
            parsed_data['sles'] = float(
                cleanup.sub("", 
                    self.soup.find('h3', {"id": "suse_images"})
                    .find_next_sibling('p')
                    .select_one('li:nth-of-type(2)')
                    .find('strong')
                    .text
                )
            ) * multiplier
        except Exception as e:
            print("Failed to load sles: %s" % e)
            pass

        try:
            parsed_data['windows_per_core'] =float(
                re.search(
                    '\$([0-9\.]+) USD/hour per visible vCPU', 
                    self.soup.find('h3', {"id": "windows_server_pricing"})
                    .find_next('ul')
                    .select_one('li:nth-of-type(2)')
                    .text
                ).group(1)
            ) * multiplier
        except  Exception as e:
            print("Failed to load windows_per_core: %s" % e)
            pass

        return parsed_data