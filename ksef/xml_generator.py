# kwasiucionek/moja-fakturownia/moja-fakturownia-a0f550ee045da0fa60a613fb7a8884b3052e00a0/ksef/xml_generator.py

from ksiegowosc.models import Invoice
from datetime import datetime
from decimal import Decimal


def _xml_escape(text):
    """Prosta funkcja do escape'owania znaków specjalnych w XML."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def generate_invoice_xml(invoice: Invoice) -> str:
    """
    Generuje fakturę w formacie XML zgodnym ze schemą FA(3).
    """
    company = invoice.user.companyinfo
    contractor = invoice.contractor

    # --- Budowanie pozycji faktury ---
    fa_wiersze_xml = ""
    for i, item in enumerate(invoice.items.all(), 1):
        fa_wiersze_xml += f"""
        <FaWiersz>
            <NrWierszaFa>{i}</NrWierszaFa>
            <P_7>{_xml_escape(item.name)}</P_7>
            <P_8A>{_xml_escape(item.unit)}</P_8A>
            <P_8B>{item.quantity}</P_8B>
            <P_9A>{item.unit_price}</P_9A>
            <P_11>{item.total_price}</P_11>
            <P_12>zw</P_12>
        </FaWiersz>
        """

    # --- Główny szablon XML ---
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Faktura xmlns="http://crd.gov.pl/wzor/2023/06/29/12648/">
    <Naglowek>
        <KodFormularza kodSystemowy="FA (3)" wersjaSchemy="1-0">FA</KodFormularza>
        <WariantFormularza>3</WariantFormularza>
        <DataWytworzeniaFa>{datetime.now().isoformat()}</DataWytworzeniaFa>
        <SystemInfo>Moja Fakturownia</SystemInfo>
    </Naglowek>
    <Podmiot1>
        <DaneIdentyfikacyjne>
            <NIP>{company.tax_id.replace("-", "")}</NIP>
            <Nazwa>{_xml_escape(company.company_name)}</Nazwa>
        </DaneIdentyfikacyjne>
        <Adres>
            <KodKraju>PL</KodKraju>
            <Ulica>{_xml_escape(company.street)}</Ulica>
            <Miejscowosc>{_xml_escape(company.city)}</Miejscowosc>
            <KodPocztowy>{_xml_escape(company.zip_code)}</KodPocztowy>
        </Adres>
    </Podmiot1>
    <Podmiot2>
        <DaneIdentyfikacyjne>
            <NIP>{contractor.tax_id.replace("-", "")}</NIP>
            <Nazwa>{_xml_escape(contractor.name)}</Nazwa>
        </DaneIdentyfikacyjne>
        <Adres>
            <KodKraju>PL</KodKraju>
            <Ulica>{_xml_escape(contractor.street)}</Ulica>
            <Miejscowosc>{_xml_escape(contractor.city)}</Miejscowosc>
            <KodPocztowy>{_xml_escape(contractor.zip_code)}</KodPocztowy>
        </Adres>
    </Podmiot2>
    <Fa>
        <KodWaluty>PLN</KodWaluty>
        <P_1>{invoice.issue_date.isoformat()}</P_1>
        <P_2>{_xml_escape(invoice.invoice_number)}</P_2>
        <P_6>{invoice.sale_date.isoformat()}</P_6>
        {fa_wiersze_xml}
        <P_13_7>{invoice.total_amount}</P_13_7>
        <P_14_7>0.00</P_14_7>
        <P_15>{invoice.total_amount}</P_15>
        <Adnotacje>
            <P_16>2</P_16>
            <P_17>1</P_17>
            <P_18>1</P_18>
            <P_18A>2</P_18A>
            <P_22>2</P_22>
            <P_23>2</P_23>
        </Adnotacje>
        <RodzajFaktury>VAT</RodzajFaktury>
    </Fa>
</Faktura>
"""
    return xml_content
