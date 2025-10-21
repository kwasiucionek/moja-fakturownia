# ksiegowosc/models.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta
import requests
from bs4 import BeautifulSoup
import re
from decimal import Decimal
from django.db.models import Sum


KODY_URZEDOW_SKARBOWYCH = [
    ("0202", "Urząd Skarbowy w Bolesławcu"),
    ("0203", "Urząd Skarbowy w Dzierżoniowie"),
    ("0204", "Urząd Skarbowy w Głogowie"),
    ("0205", "Urząd Skarbowy w Jaworze"),
    ("0206", "Urząd Skarbowy w Jeleniej Górze"),
    ("0207", "Urząd Skarbowy w Kamiennej Górze"),
    ("0208", "Urząd Skarbowy w Kłodzku"),
    ("0209", "Urząd Skarbowy w Legnicy"),
    ("0210", "Urząd Skarbowy w Lubaniu"),
    ("0211", "Urząd Skarbowy w Lubinie"),
    ("0212", "Urząd Skarbowy w Lwówku Śląskim"),
    ("0213", "Urząd Skarbowy w Miliczu"),
    ("0214", "Urząd Skarbowy w Oleśnicy"),
    ("0215", "Urząd Skarbowy w Oławie"),
    ("0216", "Urząd Skarbowy w Polkowicach"),
    ("0217", "Urząd Skarbowy w Strzelinie"),
    ("0218", "Urząd Skarbowy w Środzie Śląskiej"),
    ("0219", "Urząd Skarbowy w Świdnicy"),
    ("0220", "Urząd Skarbowy w Trzebnicy"),
    ("0221", "Urząd Skarbowy w Wałbrzychu"),
    ("0222", "Urząd Skarbowy w Wołowie"),
    ("0223", "Urząd Skarbowy w Ząbkowicach Śląskich"),
    ("0224", "Urząd Skarbowy w Zgorzelcu"),
    ("0225", "Urząd Skarbowy w Złotoryi"),
    ("0226", "Dolnośląski Urząd Skarbowy we Wrocławiu"),
    ("0227", "Pierwszy Urząd Skarbowy we Wrocławiu"),
    ("0228", "Urząd Skarbowy Wrocław-Fabryczna"),
    ("0229", "Urząd Skarbowy Wrocław-Krzyki"),
    ("0230", "Urząd Skarbowy Wrocław-Psie Pole"),
    ("0231", "Urząd Skarbowy Wrocław-Stare Miasto"),
    ("0232", "Drugi Urząd Skarbowy we Wrocławiu"),
    ("0402", "Urząd Skarbowy w Aleksandrowie Kujawskim"),
    ("0403", "Urząd Skarbowy w Brodnicy"),
    ("0404", "Urząd Skarbowy w Bydgoszczy"),
    ("0405", "Urząd Skarbowy w Chełmnie"),
    ("0406", "Urząd Skarbowy w Golubiu-Dobrzyniu"),
    ("0407", "Urząd Skarbowy w Grudziądzu"),
    ("0408", "Urząd Skarbowy w Inowrocławiu"),
    ("0409", "Urząd Skarbowy w Lipnie"),
    ("0410", "Urząd Skarbowy w Mogilnie"),
    ("0411", "Urząd Skarbowy w Nakle nad Notecią"),
    ("0412", "Urząd Skarbowy w Radziejowie"),
    ("0413", "Urząd Skarbowy w Rypinie"),
    ("0414", "Urząd Skarbowy w Sępólnie Krajeńskim"),
    ("0415", "Urząd Skarbowy w Świeciu"),
    ("0416", "Urząd Skarbowy w Toruniu"),
    ("0417", "Urząd Skarbowy w Tucholi"),
    ("0418", "Urząd Skarbowy w Wąbrzeźnie"),
    ("0419", "Urząd Skarbowy we Włocławku"),
    ("0420", "Urząd Skarbowy w Żninie"),
    ("0421", "Kujawsko-Pomorski Urząd Skarbowy"),
    ("0602", "Urząd Skarbowy w Białej Podlaskiej"),
    ("0603", "Urząd Skarbowy w Biłgoraju"),
    ("0604", "Urząd Skarbowy w Chełmie"),
    ("0605", "Urząd Skarbowy w Hrubieszowie"),
    ("0606", "Urząd Skarbowy w Janowie Lubelskim"),
    ("0607", "Urząd Skarbowy w Krasnymstawie"),
    ("0608", "Urząd Skarbowy w Kraśniku"),
    ("0609", "Urząd Skarbowy w Lubartowie"),
    ("0610", "Urząd Skarbowy w Lublinie"),
    ("0611", "Urząd Skarbowy w Łukowie"),
    ("0612", "Urząd Skarbowy w Opolu Lubelskim"),
    ("0613", "Urząd Skarbowy w Parczewie"),
    ("0614", "Urząd Skarbowy w Puławach"),
    ("0615", "Urząd Skarbowy w Radzyniu Podlaskim"),
    ("0616", "Urząd Skarbowy w Rykach"),
    ("0617", "Urząd Skarbowy w Tomaszowie Lubelskim"),
    ("0618", "Urząd Skarbowy we Włodawie"),
    ("0619", "Urząd Skarbowy w Zamościu"),
    ("0620", "Pierwszy Urząd Skarbowy w Lublinie"),
    ("0621", "Lubelski Urząd Skarbowy"),
    ("0802", "Urząd Skarbowy w Gorzowie Wielkopolskim"),
    ("0803", "Urząd Skarbowy w Krośnie Odrzańskim"),
    ("0804", "Urząd Skarbowy w Międzyrzeczu"),
    ("0805", "Urząd Skarbowy w Nowej Soli"),
    ("0806", "Urząd Skarbowy w Słubicach"),
    ("0807", "Urząd Skarbowy w Sulęcinie"),
    ("0808", "Urząd Skarbowy w Świebodzinie"),
    ("0809", "Urząd Skarbowy w Zielonej Górze"),
    ("0810", "Urząd Skarbowy w Żaganiu"),
    ("0811", "Urząd Skarbowy w Żarach"),
    ("0812", "Lubuski Urząd Skarbowy"),
    ("1002", "Urząd Skarbowy w Bełchatowie"),
    ("1003", "Urząd Skarbowy w Kutnie"),
    ("1004", "Urząd Skarbowy w Łasku"),
    ("1005", "Urząd Skarbowy w Łęczycy"),
    ("1006", "Urząd Skarbowy w Łowiczu"),
    ("1007", "Urząd Skarbowy w Łodzi"),
    ("1008", "Urząd Skarbowy w Opocznie"),
    ("1009", "Urząd Skarbowy w Pabianicach"),
    ("1010", "Urząd Skarbowy w Pajęcznie"),
    ("1011", "Urząd Skarbowy w Piotrkowie Trybunalskim"),
    ("1012", "Urząd Skarbowy w Poddębicach"),
    ("1013", "Urząd Skarbowy w Radomsku"),
    ("1014", "Urząd Skarbowy w Rawie Mazowieckiej"),
    ("1015", "Urząd Skarbowy w Sieradzu"),
    ("1016", "Urząd Skarbowy w Skierniewicach"),
    ("1017", "Urząd Skarbowy w Tomaszowie Mazowieckim"),
    ("1018", "Urząd Skarbowy w Wieluniu"),
    ("1019", "Urząd Skarbowy w Wieruszowie"),
    ("1020", "Urząd Skarbowy w Zduńskiej Woli"),
    ("1021", "Urząd Skarbowy w Zgierzu"),
    ("1022", "Pierwszy Urząd Skarbowy w Łodzi"),
    ("1023", "Drugi Urząd Skarbowy w Łodzi"),
    ("1024", "Łódzki Urząd Skarbowy"),
    ("1202", "Urząd Skarbowy w Bochni"),
    ("1203", "Urząd Skarbowy w Brzesku"),
    ("1204", "Urząd Skarbowy w Chrzanowie"),
    ("1205", "Urząd Skarbowy w Dąbrowie Tarnowskiej"),
    ("1206", "Urząd Skarbowy w Gorlicach"),
    ("1207", "Urząd Skarbowy w Krakowie"),
    ("1208", "Urząd Skarbowy w Limanowej"),
    ("1209", "Urząd Skarbowy w Miechowie"),
    ("1210", "Urząd Skarbowy w Myślenicach"),
    ("1211", "Urząd Skarbowy w Nowym Sączu"),
    ("1212", "Urząd Skarbowy w Nowym Targu"),
    ("1213", "Urząd Skarbowy w Olkuszu"),
    ("1214", "Urząd Skarbowy w Oświęcimiu"),
    ("1215", "Urząd Skarbowy w Proszowicach"),
    ("1216", "Urząd Skarbowy w Suchej Beskidzkiej"),
    ("1217", "Urząd Skarbowy w Tarnowie"),
    ("1218", "Urząd Skarbowy w Wadowicach"),
    ("1219", "Urząd Skarbowy w Wieliczce"),
    ("1220", "Urząd Skarbowy w Zakopanem"),
    ("1221", "Pierwszy Urząd Skarbowy w Krakowie"),
    ("1222", "Drugi Urząd Skarbowy w Krakowie"),
    ("1223", "Trzeci Urząd Skarbowy w Krakowie"),
    ("1224", "Czwarty Urząd Skarbowy w Krakowie"),
    ("1225", "Piąty Urząd Skarbowy w Krakowie"),
    ("1226", "Szósty Urząd Skarbowy w Krakowie"),
    ("1227", "Pierwszy Urząd Skarbowy w Tarnowie"),
    ("1228", "Małopolski Urząd Skarbowy"),
    ("1402", "Urząd Skarbowy w Białobrzegach"),
    ("1403", "Urząd Skarbowy w Ciechanowie"),
    ("1404", "Urząd Skarbowy w Garwolinie"),
    ("1405", "Urząd Skarbowy w Gostyninie"),
    ("1406", "Urząd Skarbowy w Grodzisku Mazowieckim"),
    ("1407", "Urząd Skarbowy w Grójcu"),
    ("1408", "Urząd Skarbowy w Kozienicach"),
    ("1409", "Urząd Skarbowy w Legionowie"),
    ("1410", "Urząd Skarbowy w Lipsku"),
    ("1411", "Urząd Skarbowy w Łosicach"),
    ("1412", "Urząd Skarbowy w Makowie Mazowieckim"),
    ("1413", "Urząd Skarbowy w Mińsku Mazowieckim"),
    ("1414", "Urząd Skarbowy w Mławie"),
    ("1415", "Urząd Skarbowy w Nowym Dworze Mazowieckim"),
    ("1416", "Urząd Skarbowy w Ostrołęce"),
    ("1417", "Urząd Skarbowy w Ostrowi Mazowieckiej"),
    ("1418", "Urząd Skarbowy w Otwocku"),
    ("1419", "Urząd Skarbowy w Piasecznie"),
    ("1420", "Urząd Skarbowy w Płocku"),
    ("1421", "Urząd Skarbowy w Płońsku"),
    ("1422", "Urząd Skarbowy w Pruszkowie"),
    ("1423", "Urząd Skarbowy w Przasnyszu"),
    ("1424", "Urząd Skarbowy w Przysusze"),
    ("1425", "Urząd Skarbowy w Pułtusku"),
    ("1426", "Urząd Skarbowy w Radomiu"),
    ("1427", "Urząd Skarbowy w Siedlcach"),
    ("1428", "Urząd Skarbowy w Sierpcu"),
    ("1429", "Urząd Skarbowy w Sochaczewie"),
    ("1430", "Urząd Skarbowy w Sokołowie Podlaskim"),
    ("1431", "Urząd Skarbowy w Szydłowcu"),
    ("1432", "Urząd Skarbowy w Warszawie"),
    ("1433", "Urząd Skarbowy w Węgrowie"),
    ("1434", "Urząd Skarbowy w Wołominie"),
    ("1435", "Urząd Skarbowy w Wyszkowie"),
    ("1436", "Urząd Skarbowy w Zwoleniu"),
    ("1437", "Urząd Skarbowy w Żurominie"),
    ("1438", "Urząd Skarbowy w Żyrardowie"),
    ("1439", "Pierwszy Urząd Skarbowy w Radomiu"),
    ("1440", "Pierwszy Mazowiecki Urząd Skarbowy w Warszawie"),
    ("1441", "Drugi Mazowiecki Urząd Skarbowy w Warszawie"),
    ("1442", "Trzeci Mazowiecki Urząd Skarbowy w Radomiu"),
    ("1443", "Urząd Skarbowy Warszawa-Bemowo"),
    ("1444", "Urząd Skarbowy Warszawa-Bielany"),
    ("1445", "Urząd Skarbowy Warszawa-Mokotów"),
    ("1446", "Urząd Skarbowy Warszawa-Praga"),
    ("1447", "Urząd Skarbowy Warszawa-Śródmieście"),
    ("1448", "Urząd Skarbowy Warszawa-Targówek"),
    ("1449", "Urząd Skarbowy Warszawa-Ursynów"),
    ("1450", "Urząd Skarbowy Warszawa-Wawer"),
    ("1451", "Urząd Skarbowy Warszawa-Wola"),
    ("1602", "Urząd Skarbowy w Brzegu"),
    ("1603", "Urząd Skarbowy w Głubczycach"),
    ("1604", "Urząd Skarbowy w Kędzierzynie-Koźlu"),
    ("1605", "Urząd Skarbowy w Kluczborku"),
    ("1606", "Urząd Skarbowy w Krapkowicach"),
    ("1607", "Urząd Skarbowy w Namysłowie"),
    ("1608", "Urząd Skarbowy w Nysie"),
    ("1609", "Urząd Skarbowy w Oleśnie"),
    ("1610", "Urząd Skarbowy w Opolu"),
    ("1611", "Urząd Skarbowy w Prudniku"),
    ("1612", "Urząd Skarbowy w Strzelcach Opolskich"),
    ("1613", "Pierwszy Urząd Skarbowy w Opolu"),
    ("1614", "Opolski Urząd Skarbowy"),
    ("1802", "Urząd Skarbowy w Dębicy"),
    ("1803", "Urząd Skarbowy w Jarosławiu"),
    ("1804", "Urząd Skarbowy w Jaśle"),
    ("1805", "Urząd Skarbowy w Kolbuszowej"),
    ("1806", "Urząd Skarbowy w Krośnie"),
    ("1807", "Urząd Skarbowy w Leżajsku"),
    ("1808", "Urząd Skarbowy w Lubaczowie"),
    ("1809", "Urząd Skarbowy w Łańcucie"),
    ("1810", "Urząd Skarbowy w Mielcu"),
    ("1811", "Urząd Skarbowy w Nisku"),
    ("1812", "Urząd Skarbowy w Przemyślu"),
    ("1813", "Urząd Skarbowy w Przeworsku"),
    ("1814", "Urząd Skarbowy w Ropczycach"),
    ("1815", "Urząd Skarbowy w Rzeszowie"),
    ("1816", "Urząd Skarbowy w Sanoku"),
    ("1817", "Urząd Skarbowy w Stalowej Woli"),
    ("1818", "Urząd Skarbowy w Strzyżowie"),
    ("1819", "Urząd Skarbowy w Tarnobrzegu"),
    ("1820", "Urząd Skarbowy w Ustrzykach Dolnych"),
    ("1821", "Pierwszy Urząd Skarbowy w Rzeszowie"),
    ("1822", "Podkarpacki Urząd Skarbowy"),
    ("2002", "Urząd Skarbowy w Augustowie"),
    ("2003", "Urząd Skarbowy w Białymstoku"),
    ("2004", "Urząd Skarbowy w Bielsku Podlaskim"),
    ("2005", "Urząd Skarbowy w Grajewie"),
    ("2006", "Urząd Skarbowy w Hajnówce"),
    ("2007", "Urząd Skarbowy w Kolnie"),
    ("2008", "Urząd Skarbowy w Łomży"),
    ("2009", "Urząd Skarbowy w Mońkach"),
    ("2010", "Urząd Skarbowy w Siemiatyczach"),
    ("2011", "Urząd Skarbowy w Sokółce"),
    ("2012", "Urząd Skarbowy w Suwałkach"),
    ("2013", "Urząd Skarbowy w Wysokiem Mazowieckiem"),
    ("2014", "Urząd Skarbowy w Zambrowie"),
    ("2015", "Pierwszy Urząd Skarbowy w Białymstoku"),
    ("2016", "Podlaski Urząd Skarbowy"),
    ("2202", "Urząd Skarbowy w Bytowie"),
    ("2203", "Urząd Skarbowy w Chojnicach"),
    ("2204", "Urząd Skarbowy w Człuchowie"),
    ("2205", "Urząd Skarbowy w Gdańsku"),
    ("2206", "Urząd Skarbowy w Gdyni"),
    ("2207", "Urząd Skarbowy w Kartuzach"),
    ("2208", "Urząd Skarbowy w Kościerzynie"),
    ("2209", "Urząd Skarbowy w Kwidzynie"),
    ("2210", "Urząd Skarbowy w Lęborku"),
    ("2211", "Urząd Skarbowy w Malborku"),
    ("2212", "Urząd Skarbowy w Nowym Dworze Gdańskim"),
    ("2213", "Urząd Skarbowy w Pucku"),
    ("2214", "Urząd Skarbowy w Słupsku"),
    ("2215", "Urząd Skarbowy w Sopocie"),
    ("2216", "Urząd Skarbowy w Starogardzie Gdańskim"),
    ("2217", "Urząd Skarbowy w Tczewie"),
    ("2218", "Urząd Skarbowy w Wejherowie"),
    ("2219", "Pierwszy Urząd Skarbowy w Gdańsku"),
    ("2220", "Drugi Urząd Skarbowy w Gdańsku"),
    ("2221", "Trzeci Urząd Skarbowy w Gdańsku"),
    ("2222", "Pierwszy Urząd Skarbowy w Gdyni"),
    ("2223", "Pomorski Urząd Skarbowy"),
    ("2402", "Urząd Skarbowy w Będzinie"),
    ("2403", "Urząd Skarbowy w Bielsku-Białej"),
    ("2404", "Urząd Skarbowy w Bytomiu"),
    ("2405", "Urząd Skarbowy w Chorzowie"),
    ("2406", "Urząd Skarbowy w Cieszynie"),
    ("2407", "Urząd Skarbowy w Częstochowie"),
    ("2408", "Urząd Skarbowy w Dąbrowie Górniczej"),
    ("2409", "Urząd Skarbowy w Gliwicach"),
    ("2410", "Urząd Skarbowy w Jastrzębiu Zdroju"),
    ("2411", "Urząd Skarbowy w Jaworznie"),
    ("2412", "Urząd Skarbowy w Katowicach"),
    ("2413", "Urząd Skarbowy w Kłobucku"),
    ("2414", "Urząd Skarbowy w Lublińcu"),
    ("2415", "Urząd Skarbowy w Mikołowie"),
    ("2416", "Urząd Skarbowy w Mysłowicach"),
    ("2417", "Urząd Skarbowy w Myszkowie"),
    ("2418", "Urząd Skarbowy w Pszczynie"),
    ("2419", "Urząd Skarbowy w Raciborzu"),
    ("2420", "Urząd Skarbowy w Rudzie Śląskiej"),
    ("2421", "Urząd Skarbowy w Rybniku"),
    ("2422", "Urząd Skarbowy w Siemianowicach Śląskich"),
    ("2423", "Urząd Skarbowy w Sosnowcu"),
    ("2424", "Urząd Skarbowy w Świętochłowicach"),
    ("2425", "Urząd Skarbowy w Tarnowskich Górach"),
    ("2426", "Urząd Skarbowy w Tychach"),
    ("2427", "Urząd Skarbowy w Wodzisławiu Śląskim"),
    ("2428", "Urząd Skarbowy w Zabrzu"),
    ("2429", "Urząd Skarbowy w Zawierciu"),
    ("2430", "Urząd Skarbowy w Żywcu"),
    ("2431", "Pierwszy Urząd Skarbowy w Bielsku-Białej"),
    ("2432", "Pierwszy Urząd Skarbowy w Częstochowie"),
    ("2433", "Drugi Urząd Skarbowy w Częstochowie"),
    ("2434", "Pierwszy Urząd Skarbowy w Gliwicach"),
    ("2435", "Pierwszy Urząd Skarbowy w Katowicach"),
    ("2436", "Drugi Urząd Skarbowy w Katowicach"),
    ("2437", "Pierwszy Śląski Urząd Skarbowy w Sosnowcu"),
    ("2438", "Drugi Śląski Urząd Skarbowy w Bielsku-Białej"),
    ("2602", "Urząd Skarbowy w Busku-Zdroju"),
    ("2603", "Urząd Skarbowy w Jędrzejowie"),
    ("2604", "Urząd Skarbowy w Kazimierzy Wielkiej"),
    ("2605", "Urząd Skarbowy w Kielcach"),
    ("2606", "Urząd Skarbowy w Końskich"),
    ("2607", "Urząd Skarbowy w Opatowie"),
    ("2608", "Urząd Skarbowy w Ostrowcu Świętokrzyskim"),
    ("2609", "Urząd Skarbowy w Pińczowie"),
    ("2610", "Urząd Skarbowy w Sandomierzu"),
    ("2611", "Urząd Skarbowy w Skarżysku-Kamiennej"),
    ("2612", "Urząd Skarbowy w Starachowicach"),
    ("2613", "Urząd Skarbowy w Staszowie"),
    ("2614", "Urząd Skarbowy we Włoszczowie"),
    ("2615", "Pierwszy Urząd Skarbowy w Kielcach"),
    ("2616", "Świętokrzyski Urząd Skarbowy"),
    ("2802", "Urząd Skarbowy w Bartoszycach"),
    ("2803", "Urząd Skarbowy w Braniewie"),
    ("2804", "Urząd Skarbowy w Działdowie"),
    ("2805", "Urząd Skarbowy w Elblągu"),
    ("2806", "Urząd Skarbowy w Ełku"),
    ("2807", "Urząd Skarbowy w Giżycku"),
    ("2808", "Urząd Skarbowy w Iławie"),
    ("2809", "Urząd Skarbowy w Kętrzynie"),
    ("2810", "Urząd Skarbowy w Mrągowie"),
    ("2811", "Urząd Skarbowy w Nidzicy"),
    ("2812", "Urząd Skarbowy w Nowym Mieście Lubawskim"),
    ("2813", "Urząd Skarbowy w Olecku"),
    ("2814", "Urząd Skarbowy w Olsztynie"),
    ("2815", "Urząd Skarbowy w Ostródzie"),
    ("2816", "Urząd Skarbowy w Piszu"),
    ("2817", "Urząd Skarbowy w Szczytnie"),
    ("2818", "Warmińsko-Mazurski Urząd Skarbowy"),
    ("3002", "Urząd Skarbowy w Chodzieży"),
    ("3003", "Urząd Skarbowy w Czarnkowie"),
    ("3004", "Urząd Skarbowy w Gnieźnie"),
    ("3005", "Urząd Skarbowy w Gostyniu"),
    ("3006", "Urząd Skarbowy w Grodzisku Wielkopolskim"),
    ("3007", "Urząd Skarbowy w Jarocinie"),
    ("3008", "Urząd Skarbowy w Kaliszu"),
    ("3009", "Urząd Skarbowy w Kępnie"),
    ("3010", "Urząd Skarbowy w Kole"),
    ("3011", "Urząd Skarbowy w Koninie"),
    ("3012", "Urząd Skarbowy w Kościanie"),
    ("3013", "Urząd Skarbowy w Krotoszynie"),
    ("3014", "Urząd Skarbowy w Lesznie"),
    ("3015", "Urząd Skarbowy w Nowym Tomyślu"),
    ("3016", "Urząd Skarbowy w Obornikach"),
    ("3017", "Urząd Skarbowy w Ostrowie Wielkopolskim"),
    ("3018", "Urząd Skarbowy w Ostrzeszowie"),
    ("3019", "Urząd Skarbowy w Pile"),
    ("3020", "Urząd Skarbowy w Pleszewie"),
    ("3021", "Urząd Skarbowy w Poznaniu"),
    ("3022", "Urząd Skarbowy w Rawiczu"),
    ("3023", "Urząd Skarbowy w Słupcy"),
    ("3024", "Urząd Skarbowy w Szamotułach"),
    ("3025", "Urząd Skarbowy w Śremie"),
    ("3026", "Urząd Skarbowy w Środzie Wielkopolskiej"),
    ("3027", "Urząd Skarbowy w Turku"),
    ("3028", "Urząd Skarbowy w Wągrowcu"),
    ("3029", "Urząd Skarbowy we Wrześni"),
    ("3030", "Urząd Skarbowy w Złotowie"),
    ("3031", "Urząd Skarbowy Poznań-Grunwald"),
    ("3032", "Urząd Skarbowy Poznań-Jeżyce"),
    ("3033", "Urząd Skarbowy Poznań-Nowe Miasto"),
    ("3034", "Urząd Skarbowy Poznań-Wilda"),
    ("3035", "Pierwszy Urząd Skarbowy w Poznaniu"),
    ("3036", "Wielkopolski Urząd Skarbowy"),
    ("3202", "Urząd Skarbowy w Białogardzie"),
    ("3203", "Urząd Skarbowy w Choszcznie"),
    ("3204", "Urząd Skarbowy w Drawsku Pomorskim"),
    ("3205", "Urząd Skarbowy w Goleniowie"),
    ("3206", "Urząd Skarbowy w Gryficach"),
    ("3207", "Urząd Skarbowy w Gryfinie"),
    ("3208", "Urząd Skarbowy w Kamieniu Pomorskim"),
    ("3209", "Urząd Skarbowy w Kołobrzegu"),
    ("3210", "Urząd Skarbowy w Koszalinie"),
    ("3211", "Urząd Skarbowy w Łobzie"),
    ("3212", "Urząd Skarbowy w Myśliborzu"),
    ("3213", "Urząd Skarbowy w Policach"),
    ("3214", "Urząd Skarbowy w Pyrzycach"),
    ("3215", "Urząd Skarbowy w Sławnie"),
    ("3216", "Urząd Skarbowy w Stargardzie"),
    ("3217", "Urząd Skarbowy w Szczecinie"),
    ("3218", "Urząd Skarbowy w Szczecinku"),
    ("3219", "Urząd Skarbowy w Świdwinie"),
    ("3220", "Urząd Skarbowy w Wałczu"),
    ("3221", "Pierwszy Urząd Skarbowy w Szczecinie"),
    ("3222", "Drugi Urząd Skarbowy w Szczecinie"),
    ("3223", "Zachodniopomorski Urząd Skarbowy"),
]


class CompanyInfo(models.Model):
    # Podstawowe dane identyfikacyjne
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, verbose_name="Użytkownik"
    )
    company_name = models.CharField(max_length=255, verbose_name="Pełna nazwa firmy")
    short_name = models.CharField(
        max_length=100, blank=True, verbose_name="Nazwa skrócona"
    )
    tax_id = models.CharField(max_length=20, verbose_name="NIP")
    regon = models.CharField(max_length=20, blank=True, verbose_name="REGON")
    krs = models.CharField(max_length=20, blank=True, verbose_name="KRS")
    default_social_insurance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Domyślna składka społeczna",
    )
    default_labor_fund = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Domyślna składka na Fundusz Pracy",
    )

    KSEF_ENVIRONMENTS = [
        ("test", "Środowisko testowe"),
        ("prod", "Środowisko produkcyjne"),
    ]
    ksef_environment = models.CharField(
        max_length=10,
        choices=KSEF_ENVIRONMENTS,
        default="test",
        verbose_name="Środowisko KSeF",
        help_text="Wybierz środowisko, z którym chcesz się integrować.",
    )
    ksef_token = models.CharField(
        max_length=255,  # Tokeny są długie, warto dać zapas
        blank=True,
        verbose_name="Token autoryzacyjny KSeF",
        help_text="Wygenerowany w aplikacji KSeF. Będzie bezpiecznie przechowywany.",
    )

    # Typ działalności gospodarczej
    BUSINESS_TYPES = [
        ("osoba_fizyczna", "Osoba fizyczna prowadząca działalność gospodarczą"),
        ("spolka_cywilna", "Spółka cywilna"),
        ("spolka_jawna", "Spółka jawna"),
        ("spolka_partnerska", "Spółka partnerska"),
        ("spolka_komandytowa", "Spółka komandytowa"),
        ("spolka_z_ograniczona", "Spółka z ograniczoną odpowiedzialnością"),
        ("spolka_akcyjna", "Spółka akcyjna"),
        ("inne", "Inne"),
    ]
    business_type = models.CharField(
        max_length=50,
        choices=BUSINESS_TYPES,
        default="osoba_fizyczna",
        verbose_name="Forma prawna",
    )

    # Adres
    street = models.CharField(max_length=255, verbose_name="Ulica i numer")
    zip_code = models.CharField(max_length=10, verbose_name="Kod pocztowy")
    city = models.CharField(max_length=100, verbose_name="Miasto")
    voivodeship = models.CharField(
        max_length=50, blank=True, verbose_name="Województwo"
    )
    country = models.CharField(max_length=50, default="Polska", verbose_name="Kraj")

    # Dane kontaktowe
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    fax = models.CharField(max_length=20, blank=True, verbose_name="Faks")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    website = models.URLField(blank=True, verbose_name="Strona internetowa")

    # Rachunek bankowy
    bank_account_number = models.CharField(
        max_length=34, verbose_name="Numer konta bankowego"
    )
    bank_name = models.CharField(max_length=100, blank=True, verbose_name="Nazwa banku")
    bank_swift = models.CharField(max_length=20, blank=True, verbose_name="SWIFT/BIC")

    # Opcje podatku dochodowego
    INCOME_TAX_TYPES = [
        ("skala_podatkowa", "Skala podatkowa"),
        ("podatek_liniowy", "Podatek liniowy (19%)"),
        ("ryczalt_ewidencjonowany", "Ryczałt od przychodów ewidencjonowanych"),
        ("karta_podatkowa", "Karta podatkowa"),
        ("opodatkowanie_cit", "Opodatkowanie CIT"),
    ]
    income_tax_type = models.CharField(
        max_length=50,
        choices=INCOME_TAX_TYPES,
        default="ryczalt_ewidencjonowany",
        verbose_name="Forma opodatkowania",
    )

    # Stawka ryczałtu
    LUMP_SUM_RATES = [
        ("2", "2%"),
        ("3", "3%"),
        ("5.5", "5,5%"),
        ("8.5", "8,5%"),
        ("10", "10%"),
        ("12", "12%"),
        ("14", "14%"),
        ("15", "15%"),
        ("17", "17%"),
        ("20", "20%"),
    ]

    kod_urzedu = models.CharField(
        max_length=4,
        choices=KODY_URZEDOW_SKARBOWYCH,
        blank=True,
        null=True,
        verbose_name="Kod urzędu skarbowego",
    )

    lump_sum_rate = models.CharField(
        max_length=10,
        choices=LUMP_SUM_RATES,
        default="14",
        verbose_name="Stawka ryczałtu (%)",
        blank=True,
    )

    # VAT
    VAT_SETTLEMENT_TYPES = [
        ("miesiecznie", "Miesięcznie"),
        ("kwartalnie", "Kwartalnie"),
        ("rocznie", "Rocznie"),
        ("zwolniony", "Zwolniony z VAT"),
    ]
    vat_settlement = models.CharField(
        max_length=20,
        choices=VAT_SETTLEMENT_TYPES,
        default="miesiecznie",
        verbose_name="Okres rozliczeniowy VAT",
    )

    vat_payer = models.BooleanField(default=True, verbose_name="Płatnik VAT")
    vat_id = models.CharField(max_length=20, blank=True, verbose_name="NIP UE")

    # Opcje VAT
    vat_cash_method = models.BooleanField(
        default=False, verbose_name="Metoda kasowa VAT"
    )
    small_taxpayer_vat = models.BooleanField(
        default=False, verbose_name="Mały podatnik VAT"
    )

    # ZUS
    zus_payer = models.BooleanField(default=True, verbose_name="Płatnik składek ZUS")
    zus_number = models.CharField(
        max_length=20, blank=True, verbose_name="Numer płatnika ZUS"
    )

    ZUS_CODES = [
        ("0510", "0510 - Osoba prowadząca pozarolniczą działalność gospodarczą"),
        ("0570", "0570 - Zleceniobiorca"),
        ("0590", "0590 - Osoba współpracująca"),
        ("0610", "0610 - Osoba duchowna"),
    ]
    zus_code = models.CharField(
        max_length=10,
        choices=ZUS_CODES,
        default="0510",
        verbose_name="Kod tytułu ubezpieczenia ZUS",
        blank=True,
    )

    # Opcje ZUS
    preferential_zus = models.BooleanField(
        default=False, verbose_name="Preferencyjne składki ZUS"
    )
    small_zus_plus = models.BooleanField(default=False, verbose_name="Mały ZUS Plus")
    zus_health_insurance_only = models.BooleanField(
        default=False, verbose_name="Tylko składka zdrowotna"
    )

    # Dodatkowe opcje
    pkd_code = models.CharField(max_length=10, blank=True, verbose_name="Kod PKD")
    pkd_description = models.CharField(
        max_length=255, blank=True, verbose_name="Opis działalności PKD"
    )

    # Księgowość
    ACCOUNTING_METHODS = [
        ("ksiegi_rachunkowe", "Księgi rachunkowe"),
        ("podatkowa_ksiega_przychodow", "Podatkowa księga przychodów i rozchodów"),
        ("ewidencja_ryczaltowa", "Ewidencja przychodów (ryczałt)"),
        ("karta_podatkowa", "Karta podatkowa"),
    ]
    accounting_method = models.CharField(
        max_length=50,
        choices=ACCOUNTING_METHODS,
        default="ewidencja_ryczaltowa",
        verbose_name="Forma ewidencji",
    )

    # Daty ważne
    business_start_date = models.DateField(
        null=True, blank=True, verbose_name="Data rozpoczęcia działalności"
    )
    tax_year_start = models.DateField(
        null=True, blank=True, verbose_name="Początek roku podatkowego"
    )

    # Opcje dodatkowe
    electronic_invoices = models.BooleanField(
        default=True, verbose_name="Faktury elektroniczne"
    )
    jpk_fa_required = models.BooleanField(default=True, verbose_name="Obowiązek JPK_FA")

    # Przedstawiciel ustawowy (dla spółek)
    legal_representative_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Przedstawiciel ustawowy - imię i nazwisko",
    )
    legal_representative_position = models.CharField(
        max_length=100, blank=True, verbose_name="Stanowisko"
    )

    class Meta:
        verbose_name = "Dane Firmy"
        verbose_name_plural = "Dane Firmy"

    def __str__(self):
        return self.company_name

    def get_full_address(self):
        """Zwraca pełny adres jako string"""
        return f"{self.street}, {self.zip_code} {self.city}"

    def is_vat_exempt(self):
        """Sprawdza czy firma jest zwolniona z VAT"""
        return self.vat_settlement == "zwolniony" or not self.vat_payer

    def get_tax_rate(self):
        """Zwraca stawkę podatku jako decimal"""
        if self.income_tax_type == "ryczalt_ewidencjonowany":
            return float(self.lump_sum_rate) / 100 if self.lump_sum_rate else 0.14
        elif self.income_tax_type == "podatek_liniowy":
            return 0.19
        else:
            return 0.14  # domyślnie


class Contractor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    name = models.CharField(max_length=255, verbose_name="Nazwa kontrahenta")
    tax_id = models.CharField(
        max_length=20,
        verbose_name="NIP",
        blank=True,
        null=True,
        help_text="Wypełnij, jeśli dotyczy",
    )
    street = models.CharField(
        max_length=255, verbose_name="Ulica i numer", blank=True, default=""
    )
    zip_code = models.CharField(
        max_length=10, verbose_name="Kod pocztowy", blank=True, default=""
    )
    city = models.CharField(
        max_length=100, verbose_name="Miasto", blank=True, default=""
    )

    class Meta:
        verbose_name = "Kontrahent"
        verbose_name_plural = "Kontrahenci"
        ordering = ["name"]
        unique_together = ["user", "tax_id"]  # Zapobiega duplikatom NIP per użytkownik

    def __str__(self):
        return self.name


class Invoice(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ("unpaid", "Niezapłacona"),
        ("paid", "Zapłacona"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice_number = models.CharField(max_length=50, verbose_name="Numer faktury")
    issue_date = models.DateField(default=timezone.now, verbose_name="Data wystawienia")
    sale_date = models.DateField(default=timezone.now, verbose_name="Data sprzedaży")
    payment_date = models.DateField(verbose_name="Termin płatności")
    contractor = models.ForeignKey(
        Contractor, on_delete=models.PROTECT, verbose_name="Kontrahent"
    )
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Kwota całkowita"
    )
    payment_method = models.CharField(
        max_length=50,
        choices=[("przelew", "Przelew"), ("gotówka", "Gotówka")],
        default="przelew",
        verbose_name="Sposób płatności",
    )
    payment_status = models.CharField(
        max_length=10,
        choices=PAYMENT_STATUS_CHOICES,
        default="unpaid",
        verbose_name="Status płatności",
    )
    payment_date = models.DateField(
        verbose_name="Termin płatności", blank=True, null=True
    )
    notes = models.TextField(blank=True, null=True, verbose_name="Uwagi")
    is_correction = models.BooleanField(default=False, verbose_name="Czy to korekta?")
    correction_reason = models.TextField(
        blank=True, null=True, verbose_name="Przyczyna korekty"
    )
    corrected_invoice = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corrections",
        verbose_name="Faktura korygowana",
    )

    class Meta:
        verbose_name = "Faktura"
        verbose_name_plural = "Faktury"
        ordering = ["-issue_date"]
        unique_together = ("user", "invoice_number")

    def __str__(self):
        return f"Faktura {self.invoice_number} dla {self.contractor.name}"

    def save(self, *args, **kwargs):
        # Automatycznie ustaw payment_date jeśli nie jest ustawione
        if not self.payment_date:
            self.payment_date = self.issue_date + timedelta(
                days=14
            )  # 14 dni termin płatności
        super().save(*args, **kwargs)

    def update_total_amount(self):
        """Metoda do aktualizacji sumy faktury na podstawie jej pozycji."""
        total = self.items.aggregate(total=models.Sum("total_price"))["total"] or 0.00
        self.total_amount = total
        self.save(update_fields=["total_amount"])

    @property
    def total_paid(self):
        """Suma zapłaconych kwot"""
        return self.payments.filter(status="completed").aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")

    @property
    def balance_due(self):
        """Pozostała kwota do zapłaty"""
        return self.total_amount - self.total_paid

    @property
    def is_fully_paid(self):
        """Czy faktura jest w pełni opłacona"""
        return self.balance_due <= Decimal("0.00")

    @property
    def is_overdue(self):
        """Czy faktura jest przeterminowana"""
        from django.utils import timezone

        return (
            not self.is_fully_paid
            and self.payment_date
            and self.payment_date < timezone.now().date()
        )

    @property
    def payment_status(self):
        """Status płatności faktury"""
        if self.is_fully_paid:
            return "paid"
        elif self.total_paid > 0:
            return "partial"
        elif self.is_overdue:
            return "overdue"
        else:
            return "unpaid"

    @property
    def payment_status_display(self):
        """Czytelny status płatności"""
        status_map = {
            "paid": "Opłacona",
            "partial": "Częściowo opłacona",
            "overdue": "Przeterminowana",
            "unpaid": "Nieopłacona",
        }
        return status_map.get(self.payment_status, "Nieokreślony")


class InvoiceItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice = models.ForeignKey(
        Invoice, related_name="items", on_delete=models.CASCADE, verbose_name="Faktura"
    )
    name = models.CharField(max_length=255, verbose_name="Nazwa usługi")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Ilość"
    )
    unit = models.CharField(max_length=10, default="godz.", verbose_name="J.M.")
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Cena jedn."
    )
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Wartość"
    )
    lump_sum_tax_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=14.00,
        verbose_name="Stawka ryczałtu (%)",
    )

    corrected_item = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="correction_entries",
        verbose_name="Korygowana pozycja",
    )

    class Meta:
        verbose_name = "Pozycja na fakturze"
        verbose_name_plural = "Pozycje na fakturze"

    def save(self, *args, **kwargs):
        # Automatyczne obliczanie wartości dla pozycji
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        # Po zapisaniu pozycji, aktualizujemy sumę całej faktury
        self.invoice.update_total_amount()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        # Po usunięciu pozycji, również aktualizujemy sumę
        invoice.update_total_amount()

    def __str__(self):
        return self.name


class MonthlySettlement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    month = models.IntegerField(verbose_name="Miesiąc")
    year = models.IntegerField(verbose_name="Rok")
    total_revenue = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Przychód w danym miesiącu"
    )
    health_insurance_paid = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Opłacona składka zdrowotna"
    )
    income_tax_payable = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Należny podatek dochodowy"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    social_insurance_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Opłacona składka społeczna",
    )
    labor_fund_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Opłacona składka na Fundusz Pracy",
    )

    class Meta:
        verbose_name = "Rozliczenie miesięczne"
        verbose_name_plural = "Rozliczenia miesięczne"
        unique_together = ("year", "month", "user")  # Dodano user do unique_together
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"Rozliczenie za {self.month}/{self.year}"


class YearlySettlement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    year = models.IntegerField(verbose_name="Rok")

    # Sumy z całego roku
    total_yearly_revenue = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Łączny przychód roczny"
    )
    total_social_insurance_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Łączne składki społeczne",
    )
    total_health_insurance_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Łączne składki zdrowotne",
    )
    total_labor_fund_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Łączne składki na Fundusz Pracy",
    )

    # Obliczone podatki
    total_monthly_tax_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Suma podatków z rozliczeń miesięcznych",
    )
    calculated_yearly_tax = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Obliczony podatek roczny"
    )

    # Różnica - dopłata lub zwrot
    tax_difference = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Różnica (dopłata/zwrot)"
    )

    # Stawka podatku użyta do obliczeń
    tax_rate_used = models.DecimalField(
        max_digits=4, decimal_places=2, default=14.00, verbose_name="Stawka podatku (%)"
    )

    # Dodatkowe informacje
    notes = models.TextField(blank=True, null=True, verbose_name="Uwagi")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rozliczenie roczne"
        verbose_name_plural = "Rozliczenia roczne"
        unique_together = ("year", "user")
        ordering = ["-year"]

    def __str__(self):
        return f"Rozliczenie roczne {self.year} - {self.user.username}"

    @property
    def is_overpaid(self):
        """Zwraca True jeśli zapłacono za dużo (zwrot)"""
        return self.tax_difference < 0

    @property
    def is_underpaid(self):
        """Zwraca True jeśli zapłacono za mało (dopłata)"""
        return self.tax_difference > 0

    def get_settlement_type_display(self):
        """Zwraca opis typu rozliczenia"""
        if self.is_overpaid:
            return f"Zwrot: {abs(self.tax_difference)} PLN"
        elif self.is_underpaid:
            return f"Dopłata: {self.tax_difference} PLN"
        else:
            return "Rozliczenie bez dopłat i zwrotów"


class ZUSRates(models.Model):
    year = models.IntegerField(verbose_name="Rok", unique=True)

    # Minimalne wynagrodzenie
    minimum_wage = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Płaca minimalna"
    )

    # Podstawy wymiaru składek
    minimum_base = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Minimalna podstawa wymiaru"
    )

    # Stawki składek emerytalno-rentowych
    pension_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.1976,
        verbose_name="Stawka emerytalno-rentowa (%)",
    )
    disability_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=0.015, verbose_name="Stawka rentowa (%)"
    )
    accident_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.0167,
        verbose_name="Stawka wypadkowa (%)",
    )

    # Fundusz Pracy
    labor_fund_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.0245,
        verbose_name="Stawka Fundusz Pracy (%)",
    )

    # Składka zdrowotna
    health_insurance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.09,
        verbose_name="Stawka zdrowotna (%)",
    )
    health_insurance_deductible_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.0775,
        verbose_name="Stawka zdrowotna odliczalna (%)",
    )

    # Preferencyjne składki
    preferential_pension_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.1976,
        verbose_name="Preferencja emerytalno-rentowa (%)",
    )
    preferential_months = models.IntegerField(
        default=24, verbose_name="Liczba miesięcy preferencji"
    )

    # Małe ZUS Plus - progi
    small_zus_plus_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=120000,
        verbose_name="Próg przychodów Małe ZUS Plus",
    )

    # Metadane
    updated_at = models.DateTimeField(auto_now=True)
    source_url = models.URLField(blank=True, verbose_name="Źródło danych")
    is_current = models.BooleanField(default=False, verbose_name="Aktualne stawki")

    class Meta:
        verbose_name = "Stawki ZUS"
        verbose_name_plural = "Stawki ZUS"
        ordering = ["-year"]

    def __str__(self):
        return f"Stawki ZUS {self.year}"

    def save(self, *args, **kwargs):
        # Oznacz jako aktualne tylko jedne stawki
        if self.is_current:
            ZUSRates.objects.filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)

    def calculate_social_insurance(self, company_info, annual_income=None):
        """Oblicza składki społeczne na podstawie danych firmy"""

        # Podstawa wymiaru - minimum lub 60% płacy minimalnej dla preferencji
        if company_info.preferential_zus:
            base = self.minimum_wage * Decimal("0.60")  # 60% płacy minimalnej
        elif (
            company_info.small_zus_plus
            and annual_income
            and annual_income <= self.small_zus_plus_threshold
        ):
            # Małe ZUS Plus - podstawa zależy od przychodów
            base = max(
                self.minimum_base * Decimal("0.30"),  # Min 30% podstawy
                min(
                    annual_income * Decimal("0.50") / 12, self.minimum_base
                ),  # Max podstawa minimalna
            )
        else:
            base = self.minimum_base

        # Składki społeczne
        pension_disability = base * (
            self.pension_rate + self.disability_rate
        )  # Emerytalno-rentowa
        accident = base * self.accident_rate  # Wypadkowa

        total_social = pension_disability + accident

        # Fundusz Pracy
        labor_fund = base * self.labor_fund_rate

        # Składka zdrowotna
        health_base = base  # Podstawa dla zdrowotnej
        health_total = health_base * self.health_insurance_rate
        health_deductible = health_base * self.health_insurance_deductible_rate

        return {
            "base": base,
            "social_insurance_total": total_social,
            "pension_disability": pension_disability,
            "accident": accident,
            "labor_fund": labor_fund,
            "health_insurance_total": health_total,
            "health_insurance_deductible": health_deductible,
        }

    @classmethod
    def get_current_rates(cls):
        """Pobiera aktualne stawki ZUS"""
        current_year = timezone.now().year
        rates, created = cls.objects.get_or_create(
            year=current_year,
            defaults={
                "minimum_wage": Decimal("4300.00"),  # Wartości domyślne
                "minimum_base": Decimal("4694.40"),
                "is_current": True,
                "source_url": "https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki/skladki/wysokosc-skladek-na-ubezpieczenia-spoleczne",
            },
        )
        return rates


def fetch_zus_rates_from_web(year=None):
    """Pobiera aktualne stawki ZUS ze strony ZUS.pl"""
    if year is None:
        year = timezone.now().year

    url = "https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki/skladki/wysokosc-skladek-na-ubezpieczenia-spoleczne"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Szukaj danych w tabelach lub tekście
        rates_data = {
            "year": year,
            "minimum_wage": None,
            "minimum_base": None,
            "source_url": url,
        }

        # Szukaj kwot w złotych (wzorce: 4 300,00 zł, 4300 zł, itp.)
        text_content = soup.get_text()

        # Wzorce do wyszukiwania kwot
        wage_patterns = [
            r"płaca minimalna.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"wynagrodzenie minimalne.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"(\d[\d\s]*[,.]?\d*)\s*zł.*?płaca minimalna",
        ]

        base_patterns = [
            r"podstawa wymiaru.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"minimalna podstawa.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"(\d[\d\s]*[,.]?\d*)\s*zł.*?podstawa wymiaru",
        ]

        # Próbuj wyciągnąć płacę minimalną
        for pattern in wage_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE | re.DOTALL)
            if match:
                amount_str = match.group(1).replace(" ", "").replace(",", ".")
                try:
                    amount = Decimal(amount_str)
                    if 3000 <= amount <= 10000:  # Realistyczny zakres
                        rates_data["minimum_wage"] = amount
                        break
                except:
                    continue

        # Próbuj wyciągnąć podstawę wymiaru
        for pattern in base_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE | re.DOTALL)
            if match:
                amount_str = match.group(1).replace(" ", "").replace(",", ".")
                try:
                    amount = Decimal(amount_str)
                    if 3000 <= amount <= 10000:  # Realistyczny zakres
                        rates_data["minimum_base"] = amount
                        break
                except:
                    continue

        # Wartości domyślne jeśli nie udało się wyciągnąć
        if not rates_data["minimum_wage"]:
            rates_data["minimum_wage"] = Decimal("4300.00")  # Aktualna na 2024

        if not rates_data["minimum_base"]:
            rates_data["minimum_base"] = rates_data["minimum_wage"] * Decimal(
                "1.092"
            )  # Typowo ok. 109.2% płacy minimalnej

        return rates_data

    except requests.RequestException as e:
        print(f"Błąd pobierania danych z ZUS: {e}")
        # Zwrócić wartości domyślne
        return {
            "year": year,
            "minimum_wage": Decimal("4300.00"),
            "minimum_base": Decimal("4694.40"),
            "source_url": url,
        }
    except Exception as e:
        print(f"Błąd parsowania danych ZUS: {e}")
        return {
            "year": year,
            "minimum_wage": Decimal("4300.00"),
            "minimum_base": Decimal("4694.40"),
            "source_url": url,
        }


class Payment(models.Model):
    """Płatności od klientów"""

    PAYMENT_METHODS = [
        ("przelew", "Przelew bankowy"),
        ("gotowka", "Gotówka"),
        ("karta", "Karta płatnicza"),
        ("blik", "BLIK"),
        ("paypal", "PayPal"),
        ("inne", "Inne"),
    ]

    PAYMENT_STATUS = [
        ("pending", "Oczekująca"),
        ("completed", "Zrealizowana"),
        ("cancelled", "Anulowana"),
        ("refunded", "Zwrócona"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Faktura",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Kwota")
    payment_date = models.DateField(verbose_name="Data płatności")
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="przelew",
        verbose_name="Sposób płatności",
    )
    bank_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Numer referencyjny banku"
    )
    notes = models.TextField(blank=True, verbose_name="Uwagi")
    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="completed",
        verbose_name="Status",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Płatność"
        verbose_name_plural = "Płatności"
        ordering = ["-payment_date"]

    def __str__(self):
        return f"Płatność {self.amount} PLN za {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        if not hasattr(self, "user") or not self.user:
            self.user = self.invoice.user
        super().save(*args, **kwargs)


# Kategorie kosztów
EXPENSE_CATEGORIES = [
    ("materials", "Materiały i towary"),
    ("services", "Usługi"),
    ("office", "Koszty biurowe"),
    ("transport", "Transport i paliwo"),
    ("marketing", "Marketing i reklama"),
    ("software", "Oprogramowanie i licencje"),
    ("equipment", "Sprzęt i narzędzia"),
    ("rent", "Czynsz i najem"),
    ("utilities", "Media (prąd, gaz, woda)"),
    ("insurance", "Ubezpieczenia"),
    ("legal", "Usługi prawne i doradcze"),
    ("training", "Szkolenia i rozwój"),
    ("travel", "Podróże służbowe"),
    ("maintenance", "Naprawy i konserwacja"),
    ("telecommunications", "Telekomunikacja"),
    ("other", "Inne koszty"),
]

VAT_RATES = [
    ("0", "0%"),
    ("5", "5%"),
    ("8", "8%"),
    ("23", "23%"),
    ("zw", "Zwolniony"),
    ("np", "Nie podlega"),
]


class ExpenseCategory(models.Model):
    """Kategorie kosztów dla lepszej organizacji"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    name = models.CharField(max_length=100, verbose_name="Nazwa kategorii")
    code = models.CharField(max_length=20, verbose_name="Kod kategorii")
    description = models.TextField(blank=True, verbose_name="Opis")
    is_active = models.BooleanField(default=True, verbose_name="Aktywna")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kategoria kosztów"
        verbose_name_plural = "Kategorie kosztów"
        unique_together = ["user", "code"]
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class PurchaseInvoice(models.Model):
    """Faktury zakupu - koszty działalności"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice_number = models.CharField(max_length=50, verbose_name="Numer faktury")
    supplier = models.ForeignKey(
        Contractor,
        on_delete=models.PROTECT,
        verbose_name="Dostawca",
        help_text="Kontrahent, od którego kupujemy",
    )

    # Daty
    issue_date = models.DateField(verbose_name="Data wystawienia")
    receipt_date = models.DateField(
        verbose_name="Data otrzymania", help_text="Kiedy otrzymaliśmy fakturę"
    )
    service_date = models.DateField(verbose_name="Data świadczenia usługi/dostawy")
    payment_due_date = models.DateField(
        verbose_name="Termin płatności", blank=True, null=True
    )

    # Kwoty
    net_amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Kwota netto"
    )
    vat_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Kwota VAT"
    )
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Kwota brutto"
    )

    # Kategoryzacja
    category = models.CharField(
        max_length=50,
        choices=EXPENSE_CATEGORIES,
        verbose_name="Kategoria",
        help_text="Rodzaj kosztu",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Szczegółowa kategoria",
    )

    # Opcje podatkowe
    is_deductible = models.BooleanField(
        default=True, verbose_name="Koszt uzyskania przychodu"
    )
    vat_deductible = models.BooleanField(default=True, verbose_name="VAT do odliczenia")

    # Płatności
    is_paid = models.BooleanField(default=False, verbose_name="Opłacona")
    payment_date = models.DateField(blank=True, null=True, verbose_name="Data zapłaty")
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ("transfer", "Przelew"),
            ("cash", "Gotówka"),
            ("card", "Karta"),
            ("other", "Inne"),
        ],
        default="transfer",
        verbose_name="Sposób płatności",
    )

    # Dodatkowe
    description = models.TextField(blank=True, verbose_name="Opis")
    notes = models.TextField(blank=True, verbose_name="Uwagi")
    document_file = models.FileField(
        upload_to="purchase_invoices/",
        blank=True,
        null=True,
        verbose_name="Plik faktury",
    )

    # Metadane
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Faktura zakupu"
        verbose_name_plural = "Faktury zakupu"
        ordering = ["-issue_date", "-receipt_date"]
        unique_together = ["user", "invoice_number", "supplier"]

    def __str__(self):
        return f"Faktura {self.invoice_number} od {self.supplier.name}"

    def save(self, *args, **kwargs):
        # Automatycznie oblicz total_amount jeśli nie podano
        if not self.total_amount:
            self.total_amount = self.net_amount + self.vat_amount

        # Automatycznie ustaw termin płatności jeśli nie podano
        if not self.payment_due_date:
            self.payment_due_date = self.issue_date + timedelta(days=14)

        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        """Sprawdza czy faktura jest przeterminowana"""
        if self.is_paid:
            return False
        return self.payment_due_date and self.payment_due_date < timezone.now().date()

    @property
    def days_overdue(self):
        """Ile dni przeterminowana"""
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.payment_due_date).days

    @property
    def payment_status(self):
        """Status płatności"""
        if self.is_paid:
            return "paid"
        elif self.is_overdue:
            return "overdue"
        else:
            return "pending"

    @property
    def payment_status_display(self):
        """Czytelny status płatności"""
        status_map = {
            "paid": "Opłacona",
            "overdue": "Przeterminowana",
            "pending": "Oczekuje płatności",
        }
        return status_map.get(self.payment_status, "Nieokreślony")

    def get_vat_rate_display(self):
        """Zwraca stawkę VAT w procentach"""
        if self.net_amount > 0 and self.vat_amount > 0:
            rate = (self.vat_amount / self.net_amount * 100).quantize(Decimal("0.01"))
            return f"{rate}%"
        return "0%"


class PurchaseInvoiceItem(models.Model):
    """Pozycje na fakturach zakupu"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice = models.ForeignKey(
        PurchaseInvoice,
        related_name="items",
        on_delete=models.CASCADE,
        verbose_name="Faktura",
    )

    name = models.CharField(max_length=255, verbose_name="Nazwa towaru/usługi")
    description = models.TextField(blank=True, verbose_name="Opis")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, default=1, verbose_name="Ilość"
    )
    unit = models.CharField(max_length=10, default="szt.", verbose_name="J.M.")

    unit_price_net = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Cena jedn. netto"
    )
    vat_rate = models.CharField(
        max_length=5, choices=VAT_RATES, default="23", verbose_name="Stawka VAT"
    )

    net_value = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Wartość netto"
    )
    vat_value = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Wartość VAT"
    )
    gross_value = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Wartość brutto"
    )

    category = models.CharField(
        max_length=50, choices=EXPENSE_CATEGORIES, verbose_name="Kategoria", blank=True
    )

    class Meta:
        verbose_name = "Pozycja faktury zakupu"
        verbose_name_plural = "Pozycje faktur zakupu"
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} - {self.gross_value} PLN"

    def save(self, *args, **kwargs):
        # Automatyczne obliczenia
        self.net_value = self.quantity * self.unit_price_net

        # Oblicz VAT
        if self.vat_rate == "zw" or self.vat_rate == "np":
            self.vat_value = Decimal("0.00")
        else:
            vat_rate_decimal = Decimal(self.vat_rate) / 100
            self.vat_value = self.net_value * vat_rate_decimal

        self.gross_value = self.net_value + self.vat_value

        super().save(*args, **kwargs)

        # Aktualizuj sumy na fakturze
        self.update_invoice_totals()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        # Aktualizuj sumy po usunięciu pozycji
        self.update_invoice_totals_for_invoice(invoice)

    def update_invoice_totals(self):
        """Aktualizuje sumy na fakturze na podstawie pozycji"""
        self.update_invoice_totals_for_invoice(self.invoice)

    @staticmethod
    def update_invoice_totals_for_invoice(invoice):
        """Aktualizuje sumy dla podanej faktury"""
        totals = invoice.items.aggregate(
            net_total=Sum("net_value"),
            vat_total=Sum("vat_value"),
            gross_total=Sum("gross_value"),
        )

        invoice.net_amount = totals["net_total"] or Decimal("0.00")
        invoice.vat_amount = totals["vat_total"] or Decimal("0.00")
        invoice.total_amount = totals["gross_total"] or Decimal("0.00")
        invoice.save(update_fields=["net_amount", "vat_amount", "total_amount"])


class ExpenseReport(models.Model):
    """Raporty kosztów za okresy"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    period_start = models.DateField(verbose_name="Początek okresu")
    period_end = models.DateField(verbose_name="Koniec okresu")

    total_expenses = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Łączne koszty"
    )
    deductible_expenses = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Koszty uzyskania przychodu"
    )
    vat_to_deduct = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="VAT do odliczenia"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Raport kosztów"
        verbose_name_plural = "Raporty kosztów"
        ordering = ["-period_end"]

    def __str__(self):
        return f"Koszty {self.period_start} - {self.period_end}"
