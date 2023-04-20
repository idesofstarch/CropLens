import geopandas as gpd
import pandas as pd

# TODO: Explain how each method works, in word document + output explanation
# TODO: add input files as well
# TODO: Confusion matrix for accuracy, overall accuracy and kappa value all per disease

''' Method to remove days where weather conditions are unvfavorable for a given disease, per plot
Input: disease parameter to be provided from list of diseases in main, WeatherData.xlsx, RicePestAndDisease.xlsx
Output: dataframe of weather data (per plot) with entries that satisfy disease favorable conditions
'''
def sortCandidatePlots(disease):
    # Load weather data
    weather_data = pd.read_excel('/Users/alexkamper/Desktop/WeatherData.xlsx')
    weather_data = weather_data.loc[weather_data['CropName'] == 'Paddy']

    # Load favorable weather conditions for crop disease
    disease_data = pd.read_excel('/Users/alexkamper/Desktop/RicePestAndDisease.xlsx', sheet_name='Disease')
    disease_data = disease_data.loc[disease_data['Disease name'] == disease]

    # Create a df to store which diseases each plot is at risk for
    plots_at_risk = pd.DataFrame(columns=['FarmerCode', 'Date', 'Disease'])

    disease_info = disease_data[disease_data['Disease name'] == disease].iloc[0]
    favorable_humidity = float(disease_info['Favorable Relative humidity'])
    favorable_precipitation = float(disease_info['Favorable Precipitation'])
    favorable_temperature_range = disease_info['Favorable Temperature']
    # Convert the temperature range to two separate values
    favorable_temperature_range = favorable_temperature_range.split('-')
    favorable_temperature_min = float(favorable_temperature_range[0])
    favorable_temperature_max = float(favorable_temperature_range[1])

    # remove temp extremes
    weather_data = weather_data.loc[weather_data['Tavg'] <= favorable_temperature_max]
    weather_data = weather_data.loc[weather_data['Tavg'] >= favorable_temperature_min]
    plots_at_risk = weather_data[['FarmerCode','Date']]
    plots_at_risk['Disease'] = disease
    return plots_at_risk


'''Method to find sequences of consecutive days + start date when disease conditions are favorable. For dates in a sequence, all dates except start date are removed
Input: plots_at_risk dataframe, the output of sortCandidatePlots method (parameter)
Output: dataframe of favorable dates entries, with StartDate and ConsecutiveDates columns added to show when sequence of consecutive dates began and how many
consecutive dates there were in that sequence'''
def countDiseaseDays(df):
    # convert date column to datetime format
    df['Date'] = pd.to_datetime(df['Date'])
    # sort DataFrame by FarmerCode and Date
    df = df.sort_values(by=['FarmerCode', 'Date'])
    # create empty columns for ConsecutiveDates and StartDate
    df['ConsecutiveDates'] = ''
    df['StartDate'] = ''
    # loop through each unique FarmerCode in the DataFrame
    for plot in df['FarmerCode'].unique():
        # subset DataFrame for current FarmerCode
        subset = df[df['FarmerCode'] == plot]
        # calculate consecutive dates
        cons_dates = 0
        start_date = None
        for i in range(len(subset)):
            if i == 0:
                cons_dates = 1
                start_date = subset.iloc[i]['Date']
            elif subset.iloc[i]['Date'] == subset.iloc[i-1]['Date'] + pd.DateOffset(1):
                cons_dates += 1
            else:
                # update ConsecutiveDates and StartDate columns
                subset.loc[subset.index[i-cons_dates:i], 'ConsecutiveDates'] = cons_dates
                subset.loc[subset.index[i-cons_dates:i], 'StartDate'] = start_date
                
                # reset consecutive dates and start date
                cons_dates = 1
                start_date = subset.iloc[i]['Date']
        
        # update ConsecutiveDates and StartDate columns for last set of consecutive dates
        subset.loc[subset.index[len(subset)-cons_dates:len(subset)] , 'ConsecutiveDates'] = cons_dates
        subset.loc[subset.index[len(subset)-cons_dates:len(subset)] , 'StartDate'] = start_date

        # keep only row with Date equal to StartDate
        subset = subset[subset['Date'] == subset['StartDate']]

        # update DataFrame with modified subset
        df.update(subset)

    df = df.dropna(subset=['StartDate'])
    print(df)
    return df

'''Method to set threshold for minimum consecutive dates necessary to be considered risky and to sort plots into riskiness categories
Input: dataframe output of countDiseaseDays, disease, threshold (parameters), and Paddy_plots_phase1.geojson for all plots in study area
Output: dataframe of all plots in study area with risk score in Risk column'''
def outputRiskPlots(df, disease, threshold):
    # filter the DataFrame based on a disease incubation day threshold
    condition = df['ConsecutiveDates'] >= threshold
    df = df[condition]
    sums = df.groupby('FarmerCode')['ConsecutiveDates'].sum()
    print(sums)
    plots = gpd.read_file('/Users/alexkamper/Desktop/space4good/Paddy_plots_phase1.geojson')
    merged = plots.merge(sums, left_on='Farmer_Code', right_on='FarmerCode').fillna(0)
    merged['Disease'] = disease
    # define the bins for the 'Risk' column
    bins = [-1, 0, 50, 80, float('inf')]
    labels = ['None', 'Low', 'Medium', 'High']
    # create the 'Risk' column based on the 'ConsecutiveDates' column
    merged['Risk'] = pd.cut(merged['ConsecutiveDates'], bins=bins, labels=labels)
    # convert the 'Risk' column to a regular string data type
    merged['Risk'] = merged['Risk'].astype(str)
    return merged

'''Method to validate results of weatherModel and output them to geoJSON files per disease
Input: merged dataframe - output of outputRiskPlots, disease (parameters), Yield_reducing_factors.xlsx for ground truth
Output: 1 geoJSON for each disease with Risk column and Match column to show whether Risk prediction is correct'''
def validate(df, disease):
    truth = pd.read_excel('/Users/alexkamper/Desktop/space4good/CropLens/fieldData/Yield_reducing_factors.xlsx')
    # filter the DataFrame based on current infected crops (not historical), and affirmative infection
    condition = truth['Yield reducing factor Data (Type)'] == 'Current'
    truth = truth[condition]
    condition = truth['Pest occurrence'] == 'Yes'
    truth = truth[condition]
    # Add matches column to merged df
    df['Match'] = pd.Series([])
    # Convert the disease column to separate columns when multiple
    for index, row in truth.iterrows():
        pestName = row['Pest Name'].split(',')
        # Get matching FarmerCode row from merged df
        dfRows = df[df['Farmer_Code'] == row['Farmer Code']]
        if not dfRows.empty:
            dfRow = dfRows.iloc[0]
            is_matching = 'False'
            for i in range(len(pestName)):
                search_term = pestName[i].strip()
                if (search_term.lower() == disease.lower().strip()) and (dfRow['Risk'] == 'Medium' or dfRow['Risk'] == 'High'):
                    is_matching = 'True'
                elif (dfRow['Risk'] == 'Low' or dfRow['Risk'] == 'None'): 
                    is_matching = 'True'
                    break
            dfRow['Match'] = is_matching
            df.at[dfRow.name, 'Match'] = is_matching
        else:
            print(f"No matching rows found for Farmer Code {row['Farmer Code']}")
    # Replace NaN with NoData
    df = df.fillna('NoData')
    print(df)
    directory = '/Users/alexkamper/Desktop/'
    filepath = directory + disease + 'Validated.geojson'
    df.to_file(filepath, driver='GeoJSON')
    filepath2 = directory + disease + 'Validated.xlsx'
    df.to_excel(filepath2)





if __name__ == '__main__':
    # Define the list of diseases to check
    diseases = ['Dhoma','Leaf blast','Sheath rot and grain discoloration', 'Stem rot', 'Bacterial blight','Foot rot (Bakanae)','Rice tungro','Leaf spot','False smut','Neck Blast','Brown Spot']
    # diseases = ['Dhoma']
    threshold = 10
    for disease in diseases:
        riskyPlots = sortCandidatePlots(disease)
        diseaseDays = countDiseaseDays(riskyPlots)
        merged = outputRiskPlots(diseaseDays, disease, threshold)
        validate(merged, disease)
