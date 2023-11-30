from abc import ABC, abstractmethod
import re

class GenericTable(ABC):
    name: str


    def __init__(self, rows, family_name, period) -> None:
        self.rows = rows
        self.family_name = family_name
        self.period = period
        self.indexes = {
            "od"    : self.get_index_for("price"),
            "spot"  : self.get_index_for("spot"),
            "cud1y" : self.get_index_for("1.*y"),
            "cud3y" : self.get_index_for("3.*y"),
            "cpu"   : self.get_index_for("((cpu)|(cores))"),
            "mem"   : self.get_index_for("memory"),
        }

    @abstractmethod
    def parse(self, regions) -> list:
        pass

    def get_index_for(self, name):
        list = self.rows[0]["cells"]
        query = re.compile(f'.*{name}.*', re.IGNORECASE)
        for index, row in enumerate(list):
            if query.match(row):
                return index
        return None