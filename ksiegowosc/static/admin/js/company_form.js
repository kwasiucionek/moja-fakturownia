// ksiegowosc/static/admin/js/company_form.js

document.addEventListener('DOMContentLoaded', function() {
    
    // Funkcja do pokazywania/ukrywania pól
    function toggleField(fieldId, show) {
        const field = document.querySelector(`.field-${fieldId}`);
        if (field) {
            field.style.display = show ? 'block' : 'none';
        }
    }
    
    // Obsługa pola stawki ryczałtu - pokazuj tylko gdy wybrano ryczałt
    const incomeTaxField = document.getElementById('id_income_tax_type');
    const lumpSumRateField = document.querySelector('.field-lump_sum_rate');
    
    function handleIncomeTaxChange() {
        const isLumpSum = incomeTaxField.value === 'ryczalt_ewidencjonowany';
        toggleField('lump_sum_rate', isLumpSum);
    }
    
    if (incomeTaxField) {
        incomeTaxField.addEventListener('change', handleIncomeTaxChange);
        handleIncomeTaxChange(); // Wywołaj na starcie
    }
    
    // Obsługa pól VAT - ukryj szczegóły gdy nie jest płatnikiem VAT
    const vatPayerField = document.getElementById('id_vat_payer');
    
    function handleVatPayerChange() {
        const isVatPayer = vatPayerField.checked;
        toggleField('vat_settlement', isVatPayer);
        toggleField('vat_id', isVatPayer);
        toggleField('vat_cash_method', isVatPayer);
        toggleField('small_taxpayer_vat', isVatPayer);
    }
    
    if (vatPayerField) {
        vatPayerField.addEventListener('change', handleVatPayerChange);
        handleVatPayerChange(); // Wywołaj na starcie
    }
    
    // Obsługa pól ZUS - ukryj szczegóły gdy nie jest płatnikiem ZUS
    const zusPayerField = document.getElementById('id_zus_payer');
    
    function handleZusPayerChange() {
        const isZusPayer = zusPayerField.checked;
        toggleField('zus_number', isZusPayer);
        toggleField('zus_code', isZusPayer);
        toggleField('preferential_zus', isZusPayer);
        toggleField('small_zus_plus', isZusPayer);
        toggleField('zus_health_insurance_only', isZusPayer);
    }
    
    if (zusPayerField) {
        zusPayerField.addEventListener('change', handleZusPayerChange);
        handleZusPayerChange(); // Wywołaj na starcie
    }
    
    // Obsługa przedstawiciela ustawowego - pokazuj tylko dla spółek
    const businessTypeField = document.getElementById('id_business_type');
    
    function handleBusinessTypeChange() {
        const businessType = businessTypeField.value;
        const isCompany = ['spolka_cywilna', 'spolka_jawna', 'spolka_partnerska', 
                          'spolka_komandytowa', 'spolka_z_ograniczona', 'spolka_akcyjna'].includes(businessType);
        
        toggleField('legal_representative_name', isCompany);
        toggleField('legal_representative_position', isCompany);
        
        // Rozwiń sekcję przedstawiciela jeśli to spółka
        const fieldset = document.querySelector('fieldset.collapse');
        if (fieldset && isCompany) {
            fieldset.classList.remove('collapsed');
        }
    }
    
    if (businessTypeField) {
        businessTypeField.addEventListener('change', handleBusinessTypeChange);
        handleBusinessTypeChange(); // Wywołaj na starcie
    }
    
    // Walidacja formatu NIP
    const nipField = document.getElementById('id_tax_id');
    if (nipField) {
        nipField.addEventListener('blur', function() {
            const nip = this.value.replace(/[-\s]/g, ''); // Usuń myślniki i spacje
            if (nip.length === 10 && /^\d+$/.test(nip)) {
                // Formatuj NIP: XXX-XXX-XX-XX
                this.value = nip.substring(0, 3) + '-' + nip.substring(3, 6) + '-' + 
                           nip.substring(6, 8) + '-' + nip.substring(8, 10);
            }
        });
    }
    
    // Walidacja REGON
    const regonField = document.getElementById('id_regon');
    if (regonField) {
        regonField.addEventListener('blur', function() {
            const regon = this.value.replace(/[-\s]/g, '');
            if (regon.length === 9 && /^\d+$/.test(regon)) {
                // Formatuj REGON: XXX-XXX-XXX
                this.value = regon.substring(0, 3) + '-' + regon.substring(3, 6) + '-' + regon.substring(6, 9);
            } else if (regon.length === 14 && /^\d+$/.test(regon)) {
                // Formatuj długi REGON: XX-XXX-XXX-XX-XXX
                this.value = regon.substring(0, 2) + '-' + regon.substring(2, 5) + '-' + 
                           regon.substring(5, 8) + '-' + regon.substring(8, 10) + '-' + regon.substring(10, 14);
            }
        });
    }
    
    // Walidacja kodu pocztowego
    const zipField = document.getElementById('id_zip_code');
    if (zipField) {
        zipField.addEventListener('blur', function() {
            const zip = this.value.replace(/[-\s]/g, '');
            if (zip.length === 5 && /^\d+$/.test(zip)) {
                // Formatuj kod pocztowy: XX-XXX
                this.value = zip.substring(0, 2) + '-' + zip.substring(2, 5);
            }
        });
    }
    
    // Stylowanie fieldsets
    const fieldsets = document.querySelectorAll('fieldset');
    fieldsets.forEach(function(fieldset) {
        const legend = fieldset.querySelector('h2');
        if (legend) {
            legend.style.backgroundColor = '#f8f9fa';
            legend.style.padding = '8px 12px';
            legend.style.marginBottom = '15px';
            legend.style.borderLeft = '4px solid #007cba';
            legend.style.fontWeight = 'bold';
        }
    });
    
});