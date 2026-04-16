Calculation list
1.	Care (split)
2.	Earnings
3.	Earnings (ASHE)
4.	Earnings (Award)
5.	Earnings (Split)
6.	Equipment
7.	Lost Years
8.	Pension
9.	Pension (Early Receipt)
10.	R v J
11.	Swift v Carpenter
12.	Travel
13.	Vehicle

1.Care (split)
Same as for Care but with multiple start and end dates.
Note that the start and end dates for each period need to be non-overlapping and the end date of a split is the start date of the next split.

2. Earnings

Residual Annual Earnings are taken away from Annual Earnings But For after the tax deductions have been done for both.
Residual Annual Earnings are only calculated up to retirement age and not after retirement.

Tax needs to be calculated correctly.
Tax rules differ for employed and self-employed.
Note that National Insurance tax is 0 for both employed and self-employed after retirement age.

Taxes rules for employed are:

ALGORITHM CalculateEmployeeTakeHomePay:
    INPUT: gross_salary, region (England_Wales_NI OR Scotland)
    
    // 1. CALCULATE ADJUSTED PERSONAL ALLOWANCE
    // Base allowance is £12,570. It reduces by £1 for every £2 over £100,000.
    SET personal_allowance = 12570
    IF gross_salary > 100000 THEN
        SET excess = gross_salary - 100000
        SET reduction = excess / 2
        SET personal_allowance = MAX(0, personal_allowance - reduction)
    ENDIF

    // 2. CALCULATE NATIONAL INSURANCE (NI) - 2026 Rates
    SET ni_deduction = 0
    IF gross_salary > 12570 THEN
        // 8% on the band between £12,570 and £50,270
        SET mid_band_salary = MIN(gross_salary, 50270)
        SET ni_deduction += (mid_band_salary - 12570) * 0.08
    ENDIF
    IF gross_salary > 50270 THEN
        // 2% on everything above £50,270
        SET upper_band_salary = gross_salary - 50270
        SET ni_deduction += upper_band_salary * 0.02
    ENDIF

    // 3. CALCULATE INCOME TAX
    SET income_tax = 0
    SET taxable_income = MAX(0, gross_salary - personal_allowance)

    IF region == "Scotland" THEN
        SET income_tax = CALL CalculateScottishTax(taxable_income)
    ELSE
        // England, Wales, and NI Bands (Rest of UK)
        IF taxable_income > 0 THEN
            // Basic Rate: 20% on income up to £37,700 above allowance
            SET basic_slice = MIN(taxable_income, 37700)
            SET income_tax += (basic_slice * 0.20)
        ENDIF
        IF taxable_income > 37700 THEN
            // Higher Rate: 40% on income between £37,700 and £125,140
            // Note: This band stays fixed even if personal allowance is lost
            SET higher_limit = 125140 - personal_allowance
            SET higher_slice = MIN(taxable_income, higher_limit) - 37700
            SET income_tax += (MAX(0, higher_slice) * 0.40)
        ENDIF
        IF gross_salary > 125140 THEN
            // Additional Rate: 45% on everything above £125,140
            SET additional_slice = gross_salary - 125140
            SET income_tax += (additional_slice * 0.45)
        ENDIF
    ENDIF

    // 4. FINAL CALCULATION
    SET total_deductions = income_tax + ni_deduction
    SET net_pay = gross_salary - total_deductions

    RETURN net_pay
END ALGORITHM

Taxes rule for self-employed are:
ALGORITHM CalculateSelfEmployedTax_NoDeductions:
    INPUT: annual_gross_income, region
    
    // 1. INITIALIZE PROFIT
    SET taxable_profit = annual_gross_income


    // 2. CALCULATE ADJUSTED PERSONAL ALLOWANCE
    SET personal_allowance = 12570
    IF taxable_profit > 100000 THEN
        SET reduction = (taxable_profit - 100000) / 2
        SET personal_allowance = MAX(0, 12570 - reduction)
    ENDIF

    // 3. CALCULATE CLASS 4 NATIONAL INSURANCE (NI)
    // 6% on the main band, 2% on the upper band
    SET ni_bill = 0
    IF taxable_profit > 12570 THEN
        SET ni_basic_slice = MIN(taxable_profit, 50270) - 12570
        SET ni_bill += MAX(0, ni_basic_slice) * 0.06
    ENDIF
    IF taxable_profit > 50270 THEN
        SET ni_higher_slice = taxable_profit - 50270
        SET ni_bill += ni_higher_slice * 0.02
    ENDIF

    // 4. CALCULATE INCOME TAX (English/Welsh/NI Rates)
    SET income_tax = 0
    SET taxable_income_after_pa = MAX(0, taxable_profit - personal_allowance)

    IF taxable_income_after_pa > 0 THEN
        // Basic Rate: 20%
        SET it_basic_slice = MIN(taxable_income_after_pa, 37700)
        SET income_tax += it_basic_slice * 0.20
    ENDIF

    IF taxable_income_after_pa > 37700 THEN
        // Higher Rate: 40% (Note: Upper limit is 125,140 total income)
        SET it_higher_limit = 125140 - personal_allowance
        SET it_higher_slice = MIN(taxable_income_after_pa, it_higher_limit) - 37700
        SET income_tax += MAX(0, it_higher_slice) * 0.40
    ENDIF

    IF taxable_profit > 125140 THEN
        // Additional Rate: 45%
        SET it_additional_slice = taxable_profit - 125140
        SET income_tax += it_additional_slice * 0.45
    ENDIF

    // 5. TOTAL YEARLY TAX LIABILITY
    SET total_tax_year_bill = income_tax + ni_bill


3. Earnings (ASHE)
Same tax rules apply here as the above Earnings.

We need to map the claimants job to the correct ASHE Code.
ASHE codes are provided in the link that has been sent.
For each job ASHE code we can select the appropriate table for the earnings calculation
 

We can also selected the appropriate dataset. We want to have this as a parameter however so we can change the dataset.
 

4. Earnings (award)
This is a one off payment that is given for the current age of the claimant when it is entered and is not taxable.
5. Earnings (split)
Same considerations apply as to Earnings except that now we consider multiple periods. Not again that a previous period end date is the next periods start date.
6. Equipment 
This calculation always shows the cost of the equipment as the annual cost regardless of the replacement schedule. The complexity of this calculation is only in the multiplier.
7. Lost Years
This calculation is only relevant for impair life expectancy,
The Lost Years are calculated for Earnings and Pensions.
Lost Years are only calculated from the start of the expected reduction in Life Expectancy which is a global setting as shown below.
 
It is also possible to define a impaired life expectancy before the accident – a per conditioned reduced life expectancy as shown below
 
The effect of setting a pre conditioned reduced life expectancy is that this becomes the new default life expectancy rather than the relevant average life expectancy number.
All tax calculations are the same as other tax calculations in earnings above. 
Pension Lump sums are not taxed.
Pension Lump sums are only included if they occur after the years of expected reduced life expectancy.
For any period (only years after the reduced expected life expectancy count) the amount taxed is the gross earnings + gross pension annual amount.

8. Pension
But For Pension is calculated using the same tax calculations (No NI after state retirement age)
Residual Pension is calculated after tax and taken away from the total sum (total sum = But For Pension after tax – Residual Pension after tax)
Note Pensions are only calculated up to any impaired Life Expectancy age.
9. Pension (Early receipt)
Need to confirm how to calculate
10. R v J
If betterment costs are greater than adaptation costs then the total of these two costs is 0.
If betterment costs are less than adaptation costs then total is = adaptation costs – betterment costs.
The calculation for is:
(Cost of required property – value of current property + Betterment Costs) * Rate (note: rate defaults to discount rate 0.5%) + Increase annual running costs + max(adaptation costs – betterment costs, 0)
11. Swift vs Carpenter
The calculation is:
(Cost of required property – value of current property)
Then calculate the discount multiplier, DM,  for the time period defined in inputs at 5% (this method will be provided)
Then (Cost of required property – value of current property) X DM = Revisionary Interest
Final amount, Life Interest, = Cost of required property – value of current property - Revisionary Interest
12. Travel
Travel costs can be easily seen how to calculate from the input examples below and the corresponding output
 
 

Note that given the various recurring time period options below
 
We will need to use the same type of calculation of annualised hours (rate) as we did with the Care costs defined in the first document.

13.	Vehicle
See inputs below
 
And corresponding outputs
 


Calculation is:
Cost of New Vehicle – Credit for own vehicle
Now calculate the Number of Purchases over Time Period given different frequencies as shown below
 

Again we work out the number of the selected time increments over the time period using a look up for those dates.

Total cost of annual replacement is 
Cost of New Vehicle – Trade In Value.
See an example for the replacement period set as months instead of years
Inputs
 
Outputs
 
Calculate the Number of Purchases Over Total Time period given Replacement frequency.




