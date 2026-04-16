CALCULATION LOGIC

Input Logic:
Step 1: Define Start_Date/ Age_At_Start (Date format or Float) AND End_Date / Age_At_End (Date format or Float)
Step 2: Define Number_Of_Hours  (Float) AND Time_Increment (which can be one of Over_Period, Per_Day, Per_Week, Per_Month, Per_Year, Per_Weekday, Per_Weekend, Per_Monday, Per_Tuesday, Per_Wednesday, Per_Thursday, Per_Friday, Per_Saturday, Per_Sunday, Per_Day_Specify, Per_Week_Specify, Per_Month_Specify, Per_Weekday_Specify, Per_Weekend_Specify)
Step 3: Define Care_Rate (which can be one of Aggregate_Rate, Basic_Rate, Evening_Rate, Weekend_Rate, Saturday_Rate, Sunday_Rate, Aggregate_Day_Rate, Specify_Rate) AND Percentage_Less (Float)

Step 4:
IF in Step 3 Specify_Rate was selected THEN enter Manual_Rate (Float)

Step 5:
 IF in Step 2
 Per_Day_Specify was selected THEN define Number_Days_Specify (Float) AND Specify_Increment (which can be one of Over_Period_Specify, Per_Week_Specify, Per_Month_Specify, Per_Year_Specify)

ELSE IF

Per_Week_Specify was selected THEN define Number_Weeks_Specify (Float) AND Specify_Increment (which can be one of Over_Period_Specify, Per_Week_Specify, Per_Month_Specify, Per_Year_Specify)

ELSE IF

 Per_Month_Specify was selected THEN define Number_Months_Specify (Float) AND Specify_Increment (which can be one of Over_Period_Specify, Per_Week_Specify, Per_Month_Specify, Per_Year_Specify)

ELSE IF

Per_Weekday_Specify was selected THEN define Number_Weeks_Specify (Float) AND Specify_Increment (which can be one of Over_Period_Specify, Per_Week_Specify, Per_Month_Specify, Per_Year_Specify)

ELSE IF

Per_Weekend_Specify  was selected THEN define Number_Weeks_Specify (Float) AND Specify_Increment (which can be one of Over_Period_Specify, Per_Week_Specify, Per_Month_Specify, Per_Year_Specify)

Output Logic:

Step 1:
Calculate_Period_Years :
End_Date / Age_At_End (Date format or Float)   -   Start_Date/ Age_At_Start (Date format or Float) 
Step 2:
Calculate Annualised Hours AND Annualised Cost
IF Time_Increment = Over_Period, 
THEN
AnnualisedHours = Number_Of_Hours  (Float)  /  Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

…………………………………………
ELSE IF 
Time_Increment  = Per_Day, 

AnnualisedHours = Total_Number_Of_Hours (Note: Lookup number of days during period x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


…………………………………
ELSE IF
Time_Increment  = Per_Week, 
THEN
AnnualisedHours = Total_Number_Of_Hours (Note: Lookup number of weeks during period x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….
ELSE IF
Time_Increment  = Per_Month, 
AnnualisedHours = Total_Number_Of_Hours (Note: Lookup number of months during period x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….

ELSE IF
Time_Increment  = Per_Year, 
THEN
AnnualisedCost = AnnualisedHours (Number_Of_Hours) X Care_Rate

………………………………………………………………………….
ELSE IF
Time_Increment  = Per_Weekday, (Note: We have additional option to include or exclude public holidays)
THEN
AnnualisedHours = Total_Number_Of_Hours (Note: Lookup number of working days during period (NOTE: Include option to include or exclude public holidays in count)   X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….

ELSE IF
Time_Increment  = Per_Weekend, 
THEN
AnnualisedHours = Total_Number_Of_Hours (Note: Lookup number of weekends during period X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….
ELSE IF
Time_Increment  = Per_Monday OR Per_Tuesday OR Per_Wednesday OR Per_Thursday OR Per_Friday, Per_Saturday OR Per_Sunday
THEN
AnnualisedHours = Total_Number_Of_Hours (Lookup number of Mondays/Tuesdays/ect during period X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….
ELSE IF
Time_Increment =  Per_Day_Specify AND Specify_Increment = Over_Period_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Days_Specify x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

ELSE IF
Time_Increment =  Per_Day_Specify AND Specify_Increment  = Per_Week_Specify
AnnualisedHours = Total_Number_Of_Hours (Look up Total Number of Weeks x Number_Days_Specify X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

ELSE IF

Time_Increment =  Per_Day_Specify AND Specify_Increment  = Per_Month_Specify

AnnualisedHours = Total_Number_Of_Hours (Look up Total Number of Months x Number_Days_Specify X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

ELSE IF
 Time_Increment =  Per_Day_Specify AND Specify_Increment  = Per_Year_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Days_Specify X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….

ELSE IF
Time_Increment  = Per_Week_Specify AND Specify_Increment = Over_Period_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


(Time_Increment  = Per_Week_Specify AND Specify_Increment = Per_Week_Specify – THIS OPTIONS DOESN’T APPLY)
ELSE IF

Time_Increment  = Per_Week_Specify AND Specify_Increment = Per_Month_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x NumberOf MonthsInPeriod X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

ELSE IF


Time_Increment  = Per_Week_Specify AND Specify_Increment = Per_Year_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

………………………………………………………………………….
ELSE IF
Time_Increment  = Per_Month_Specify AND Specify_Increment = Over_Period_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Months_Specify x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


ELSE IF

Time_Increment  = Per_Month_Specify AND Specify_Increment = Per_Week_Specify

(Note: This option does not make sense and so can be ignored – Can not have months per week)
ELSE IF

Time_Increment  = Per_Month_Specify AND Specify_Increment = Per_Month_Specify

(Note: This option does not make sense and so can be ignored – Can not have months per months)

ELSE IF

Time_Increment  = Per_Month_Specify AND Specify_Increment = Per_Year_Specify

AnnualisedHours = Total_Number_Of_Hours (Number_Months_Specify X Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


……………………………………………………………………………..
ELSE IF
Time_Increment  = Per_Weekday_Specify AND Specify_Increment = Over_Period_Specify

AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


ELSE IF

Time_Increment  = Per_Weekday_Specify AND Specify_Increment = Per_Week_Specify

(Note: This option does not make sense and so can be ignored – Can not have weekday per weeks)


ELSE IF

Time_Increment  = Per_Weekday_Specify AND Specify_Increment = Per_Month_Specify

AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x NumberOfMonthsInPeriod x Number_Of_Hours  X 5)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate

ELSE IF

Time_Increment  = Per_Weekday_Specify AND Specify_Increment = Per_Year_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x Number_Of_Hours X 5)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate





…………………………………………………………………………….
ELSE IF
Time_Increment  = Per_Weekend_Specify AND Specify_Increment = Over_Period_Specify
AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x Number_Of_Hours)/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


ELSE IF

Time_Increment  = Per_Weekend_Specify AND Specify_Increment = Per_Week_Specify


(Note: This option does not make sense and so can be ignored – Can not have weekends per weeks)

ELSE IF

Time_Increment  = Per_Weekend_Specify AND Specify_Increment = Per_Month_Specify

AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x NumberOfMonthsInPeriod x Number_Of_Hours )/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate


ELSE IF

Time_Increment  = Per_Weekend_Specify AND Specify_Increment = Per_Year_Specify

AnnualisedHours = Total_Number_Of_Hours (Number_Weeks_Specify x Number_Of_Hours )/ Calculate_Period (Years)
AnnualisedCost = AnnualisedHours X Care_Rate




