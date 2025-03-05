import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import streamlit as st
from datetime import datetime as t, timedelta as td, time
import datetime as dt
import numpy as np
import plotly.express as px


#Extract Date from string - 1 or 2 numbers followed by any number of letters followed by 2 or 4 numbers
def extract_date(text):
    date_pattern = r'(\d{1,2}\s\w+\s\d{4})|(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})'
    match = re.search(date_pattern, text)
    if match:
        try:
            date_text = match.group()
            return date_text, text.replace(date_text,'').strip()
        except ValueError:
            return None, text
    return None, text

#Speed = Dist / Time
def Speed(d,t):
    return d / t

#Convert datetime into seconds for speed calc (inc handling poor data quality)
def time_in_seconds(time_str):
    if pd.isnull(time_str) or time_str in ('nan', '1 Lap', 'DNF', '?', 'Dangerous riding x 2'):
        return np.nan
    h,m,s = map(int,time_str.split(':'))
    return h*3600+m*60+s

#Setting to null DQ issues and setting Position as an int
def Pos_Cleanse(Position):
    if pd.isnull(Position) or Position in ('1 Lap', 'DQ Dangerous riding', 'DQ Cutting Corner', 'DQ Abuse of Marshal', 'DQ - Drafting', 'DQ'):
        return np.nan
    return str(Position)

#Return left of . in a string
def Left_String(Pos):
    Left = Pos.split('.')[0]
    return Left

#Add timedelta components to time
def add_time(start_time, delta):
    start_minutes = start_time.hour * 60 + start_time.minute #+ 
    add_minutes = int(delta.total_seconds()//60)
    total_minutes = start_minutes + add_minutes
    hours = (total_minutes//60)%24
    minutes = total_minutes%60
    return time(hour=hours, minute=minutes)
#pd.Timestamp(hours=hours, minutes=minutes).time()


#Variables for HTML requests
urls = ["https://swindon-rc.co.uk/?page_id=240","https://swindon-rc.co.uk/?page_id=590"]


#Variables for Excel data import
df_excel = pd.read_excel("TT results 2015 - 2022.xlsx", header=None)

df_excel.columns = ['Position','Start Number','Name','Club','Split Time','Time','Comments']

DateIndex = []

Del = []

d=10
sd = 9.1
hd = 5.2

#HTML data
@st.cache_data
def HTML_Data(URLS):
    combined_df_HTML = pd.DataFrame()
#Find all figure objects
    for url in URLS:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        figures = soup.findAll('figure')
        #Find previous paragraph objects
        for f in figures:
            table = f.find('table')
            prev_element = f.find_previous('p')
            date_text = None
            Comments = []
            check = 0
        
            while prev_element and check <3:
                para_text = prev_element.get_text()
                #Handling data quality
                if para_text == '2 June 202310 August 2023':
                    prev_element = prev_element.find_previous('p')
                    continue
                #Append non-date paragraphs to Comments
                date_text, remaining_text = extract_date(para_text)
                if date_text:
                    Comments.append(remaining_text)
                    break
                else:
                    Comments.append(para_text)
                prev_element = prev_element.find_previous('p')
                check += 1
        
            if date_text or Comments:
                df_HTML = pd.read_html(str(table), header=0)[0]

                df_HTML['Road Bike'] = ''

                rows = table.find_all('tr')
                data_row_index = 0
                #Handles 'Names in italics denote Road Bike' and sets Road Bike column to be 'RB' if true
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 0:
                        is_italic = any(cell.find('em') for cell in cells)
                        if is_italic:
                            df_HTML.at[data_row_index-1, 'Road Bike'] = 'RB'
                        data_row_index += 1

                if date_text:
                    df_HTML['Date'] = date_text
                if Comments:
                    df_HTML['Comments'] = ''.join(Comments[::-1])

                df_HTML.columns = ['Position', 'Start Number', 'Name', 'Club', 'Split Time', 'Time','Speed m.p.h','Road Bike','Date','Comments']        

            combined_df_HTML = pd.concat([combined_df_HTML,df_HTML], ignore_index=True)

    #Data cleansing and sorting
    combined_df_HTML['Position'] = combined_df_HTML['Position'].astype(str).str.replace('= ','').apply(Pos_Cleanse)
    combined_df_HTML['Position'] = combined_df_HTML['Position'].astype(float)

    combined_df_HTML['Date'] = pd.to_datetime(combined_df_HTML['Date'])
    combined_df_HTML = combined_df_HTML.sort_values(by=['Date','Position'],ascending=[False,True])

    combined_df_HTML['Position'] = combined_df_HTML['Position'].astype(str).apply(Left_String)

    #Remove '-' from Comments
    if 'Comments' in combined_df_HTML.columns:
        combined_df_HTML['Comments'] = combined_df_HTML['Comments'].str.replace('– ','')
    return combined_df_HTML



@st.cache_data
def Excel_Data(Excel):
    #Excel
    #Identify the index position of every date row in the Excel
    for i in Excel['Position']:
        if isinstance(i, dt.datetime):
            Ind = Excel.index.get_loc(Excel[Excel['Position']==i].index[0])
            DateIndex.append([i,Ind])
    
    #Append the date between the above index positions
    for i, sublist in enumerate(DateIndex):
        Start = sublist[1]
        if i+2 > len(DateIndex):
            End = Excel.shape[0]
        else:
            End = DateIndex[i+1][1]
        Excel.loc[Start:End,'Date'] = sublist[0]


    #Drop all of the date rows
    for i in Excel['Position']:
        if isinstance(i, dt.datetime): 
            Del.append(Excel.index.get_loc(Excel[Excel['Position']==i].index[0]))

    Excel.drop(Del,inplace=True)

    #Convert time columns from datetime to string
    Excel['Time'] = Excel['Time'].astype(str)
    Excel['Split Time'] = Excel['Split Time'].astype(str)
    #Convert time into seconds
    Excel['Time in Seconds'] = Excel['Time'].apply(time_in_seconds)
    Excel['Split Time in Seconds'] = Excel['Split Time'].apply(time_in_seconds)
    #Use split time if time is null etc - see time_in_seconds function
    Excel['Effective Time in Seconds'] = Excel['Time in Seconds'].combine_first(Excel['Split Time in Seconds'])
    #Use the correct distance
    Excel['Half Distance?'] = np.where(((Excel['Effective Time in Seconds'] == Excel['Split Time in Seconds'])|(Excel['Comments']== 'Prologue - 5.2 miles')),hd,d)
    Excel['Actual Distance'] = np.where(Excel['Comments']=='A shortened course of 9.1 miles due to roadworks',sd,Excel['Half Distance?'])

    #Calculate speed
    Excel['Speed m.p.h'] = (Speed(Excel['Actual Distance'],Excel['Effective Time in Seconds'])*3600)

    Excel['Speed m.p.h'] = Excel['Speed m.p.h'].round(2)
    Excel['Position'] = Excel['Position'].astype(str).str.replace('= ','')
    Excel['Position'] = Excel['Position'].str.replace('=','')
    Excel['Position'] = Excel['Position'].apply(Pos_Cleanse)
    Excel['Position'] = Excel['Position'].astype(float)
    Excel['Position'] = Excel.groupby('Date')['Position'].transform(lambda x: x.fillna(x[x.notna()].max()+1))
    Excel['Position'] = Excel['Position'].astype(str).apply(Left_String)


    Excel.drop(columns=['Time in Seconds','Split Time in Seconds','Effective Time in Seconds','Actual Distance','Half Distance?'],inplace=True)

    Excel['Road Bike'] = ''

    Excel = Excel[['Position','Start Number','Name','Club','Split Time','Time','Speed m.p.h','Road Bike','Date','Comments']]

    return Excel

#Presentation
st.set_page_config(layout='wide')

st.title("Latton TT Series")
combined_df_HTML = HTML_Data(urls)
df_Excel = Excel_Data(df_excel)


df = pd.concat([combined_df_HTML,df_Excel])

df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%d %B %Y')


df = df.reset_index(drop=True)

#StartTime = date.strptime('18:16:00','%H:%M:%S')
StartTime = time(18,16,0)
#pd.Timestamp(hour=18,minute=16).time()#dt.

df['Start Number'] = df['Start Number'].apply(lambda x: 0 if pd.isna(x) else x)

df['Add Time']=df['Start Number'].apply(lambda x: td(minutes=(x-1)))
df['Start Time']=df['Add Time'].apply(lambda delta: add_time(StartTime, delta))
df.drop(columns=['Add Time'], inplace=True)

df.columns = ['Position', 'Start Number', 'Name', 'Club', 'Split Time', 'Time','Speed m.p.h','Road Bike','Date','Comments','Start Time']


#Unique list of racers names
Names = df.Name.drop_duplicates()
Names.sort_values(ascending=True, inplace=True)

#Unique list of Weeks
Date = df.Date.drop_duplicates()
Sorted_Date = Date.iloc[pd.to_datetime(Date, format='%d %B %Y').argsort()[::-1]]

#Present text
#Basic dropdowns
Date = st.multiselect("Enter date to filter the results",list(Date))
Racer = st.multiselect("Enter your name to filter the results",list(Names))



DataTab, GraphTab = st.tabs(["Data","Graphs"])
with DataTab:
#Table
    if (Date and Racer):
        rslt_df1 = df[df['Date'].isin(Date)]
        rslt_df = rslt_df1[rslt_df1['Name'].isin(Racer)]
    elif Racer:
        rslt_df = df[df['Name'].isin(Racer)]
    elif Date:
        rslt_df = df[df['Date'].isin(Date)]
    else:
        rslt_df = df

    rslt_df1 = rslt_df.loc[:,rslt_df.columns != 'Start Time']
    st.dataframe(rslt_df1,hide_index=True)

plot_df = rslt_df.iloc[::-1]
plot_df['Date'] = pd.to_datetime(plot_df['Date'], format='%d %B %Y')

#fig_by_Speed = px.line(plot_df, x="Date", y="Speed m.p.h", color="Name")
#fig_by_Speed.update_traces(hovertemplate='%{x|%d-%b-%Y}<br>Speed: %{y}')
#fig_by_Speed.update_traces(customdata=plot_df[['Date']])

#fig_by_Position = px.line(plot_df, x="Date", y="Position", color="Name")
#fig_by_Position.update_layout(yaxis = dict(autorange="reversed"))
#fig_by_Position.update_traces(hovertemplate='%{x|%d-%b-%Y}<br>Position: %{y}')
#fig_by_Position.update_traces(customdata=plot_df[['Date']])


#fig_by_Start = px.scatter(plot_df, x="Start Number", y="Time", color="Name")
#fig_by_Start.update_yaxes(categoryorder="category descending")

#with GraphTab:
    Select = st.selectbox("Choose which graph you would like to view",('Split Time','Time','Speed m.p.h','Position'))
    if not Racer:
        st.write("Please select a racer from the name filter above to present graphs")
    else:
        if Select=="Position":
            fig_All = px.line(plot_df, x="Date", y="Position", color="Name")
            fig_All.update_yaxes(categoryorder="category descending")
            st.plotly_chart(fig_All)
        else:
            fig_All = px.line(plot_df, x="Date", y=Select, color="Name")
            st.plotly_chart(fig_All)
#        SpeedTab, PositionTab, TimeTab, StartTab = st.tabs(["Speed", "Position", "Time", "Start Time"])
#        with SpeedTab:
#            st.write(fig_by_Speed)
#        with PositionTab:
#            st.write(fig_by_Position)
#        with TimeTab:
#            Time = st.selectbox("Split Time or Full Time",('Split Time','Time'))
#            fig_by_Time = px.line(plot_df, x="Date", y=Time, color="Name")
#            fig_by_Time.update_yaxes(categoryorder="category descending")
#            fig_by_Time.update_traces(hovertemplate='%{x|%d-%b-%Y}<br>Time: %{y}')
#            fig_by_Time.update_traces(customdata=plot_df[['Date']])
#            st.write(fig_by_Time)
#        with StartTab:
#            st.write(fig_by_Start)
