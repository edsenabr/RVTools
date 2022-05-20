from __future__ import annotations
import openpyxl
from timebudget import timebudget
timebudget.set_quiet()  # don't show measurements as they happen


class CellFormat:
    thin = openpyxl.styles.Side(border_style="thin", color="000000")
    thin_border = openpyxl.styles.Border(top=thin, left=thin, right=thin, bottom=thin)

    bold_font = openpyxl.styles.Font(bold=True)
    colors = {}
    alignment = openpyxl.styles.alignment.Alignment(horizontal="center", vertical="center")
    currency_format = '[$$-409]#,##0.00'
    gb_format = '0.0 "GB"'    
    tb_format = '0.0 "TB"'
    sheet = openpyxl.worksheet.worksheet.Worksheet(None)

    def get_color(self, color: str):
        if not color in self.colors:
            self.colors[color] = openpyxl.styles.PatternFill("solid", color)
        return self.colors[color]


    @timebudget
    def __init__(self, sheet=None):
        self.has_border = False
        self.is_centered = False
        self.is_bold = False
        self.is_currency = False
        self.is_gb = False
        self.is_tb = False
        self.fill_color = None
        self.data = None
        if not sheet is None:
            self.sheet = sheet

    @timebudget
    def border(self, color:str="000000") -> CellFormat:
        self.has_border = True
        return self

    @timebudget
    def color(self, color:str) -> CellFormat:
        if not color is None:
            self.fill_color = self.get_color(color)
        return self

    @timebudget
    def value(self, value:str) -> CellFormat:
        cell = openpyxl.cell.cell.Cell(self.sheet, column=1, row=1, value=value)
        return self.apply(cell)

    @timebudget
    def alternate_color(self, index:int) -> CellFormat:
        if not (index % 2):
            return self.color('EEEEEE')
        return self

    @timebudget
    def center(self) -> CellFormat:
        self.is_centered = True
        return self

    @timebudget
    def bold(self) -> CellFormat:
        self.is_bold = True
        return self

    @timebudget
    def currency(self) -> CellFormat:
        self.is_currency = True
        self.is_gb = False
        self.is_tb = False
        return self

    @timebudget
    def gb(self) -> CellFormat:
        self.is_currency = False
        self.is_gb = True
        self.is_tb = False
        return self

    @timebudget
    def tb(self) -> CellFormat:
        self.is_currency = False
        self.is_gb = False
        self.is_tb = True
        return self

    @timebudget
    def header(self, color:str) -> CellFormat:
        return self.border().bold().center().color(color)

    @timebudget
    def apply(self, cell):
        if (self.is_bold):
            cell.font = self.bold_font

        if (self.has_border):
            cell.border = self.thin_border

        if self.is_centered:
            cell.alignment = self.alignment

        if not self.fill_color is None:
            cell.fill = self.fill_color

        if self.is_currency:
            cell.number_format = self.currency_format

        if self.is_gb:
            cell.number_format = self.gb_format

        if self.is_tb:
            cell.number_format = self.tb_format

        # if not self.value is None:
        #     cell.value = self.data

        return cell

    @timebudget
    def generator(self, sheet, row):
        for index, cell in enumerate(row):
            yield self.apply(
                openpyxl.cell.cell.Cell(
                    sheet, 
                    column="A", 
                    row=1, 
                    value=cell
                )
            )