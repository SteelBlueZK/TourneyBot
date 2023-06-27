import os
import selenium as sl
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.alert import Alert
import pprint
import json
import time

pp = pprint.PrettyPrinter(depth=4)

playerListFile = '../players'
roomListFile = '../roomNames'
stateFile = '../state'
loginFile = '../loginDetails'
prefix = 'FC '


def WriteState(state):
	with open(stateFile + '.json', 'w') as outfile:
		json.dump(state, outfile, indent=4)


def ReadState():
	with open(stateFile + '.json', 'r') as f:
		return json.load(f)


def LoadFileToList(fileName):
	with open('{}.txt'.format(fileName)) as file:
	    lines = [line.rstrip() for line in file]
	return lines


def ListRemove(myList, element):
	if element not in myList:
		return myList
	myList = myList.copy()
	myList.remove(element)
	return myList


def DictRemove(myDict, element):
	if element not in myDict:
		return myDict
	myDict = myDict.copy()
	myDict.pop(element)
	return myDict


def GetListInput(question, choices):
	for i, choice in enumerate(choices):
		question = question + ' [{}] {},'.format(i + 1, choice)
	question = question[:-1] + ': '
	
	validResponses = [str(i + 1) for i in range(len(choices))]
	response = input(question)
	while response not in (validResponses + choices):
		response = input(question)
	if response in choices:
		return response
	return choices[int(response) - 1]


def InitialiseWebDriver():
	loginDetails = LoadFileToList(loginFile)
	# Using Chrome to access web
	driver = sl.webdriver.Chrome()# Open the website
	
	driver.get('https://zero-k.info')
	driver.implicitly_wait(0.5)
	
	nameBox = driver.find_element(By.NAME, 'login')
	nameBox.send_keys(loginDetails[0])
	
	
	nameBox = driver.find_element(By.NAME, 'password')
	nameBox.send_keys(loginDetails[1])
	
	login_button = driver.find_element(By.NAME,'zklogin')
	login_button.click()
	
	driver.get('https://zero-k.info/Tourney')
	driver.implicitly_wait(0.5)
	return driver


def ProcessTableRow(row):
	elementList = row.find_elements(By.XPATH, ".//*")
	elements = {e.text : e for e in elementList}
	elementNames = list(elements.keys())
	rowData = {}
	if 'Force join' in elements:
		rowData['forceJoin'] = elements['Force join']
	if 'Delete' in elements:
		rowData['delete'] = elements['Delete']
	
	rowData['playersJoined'] = (elementNames[0].count('  IN') > 1)
		
	if elementNames[4] == '  IN':
		rowData['players'] = [elementNames[3], elementNames[5]]
	else:
		rowData['players'] = [elementNames[3], elementNames[4]]
	
	selectNext = False
	for name, element in elements.items():
		if selectNext and element.text.count(' ') == 0:
			rowData['battleID'] = element.text[1:]
			break
		if name.count(' 2 on ') > 0:
			selectNext = True
	return elementNames[1], rowData


def GetRoomTable(driver):
	tables = driver.find_elements(By.TAG_NAME, 'table')
	elements = False
	for table in tables:
		if table.text.count('Force join') > 0:
			elements = table.find_elements(By.XPATH, ".//*")
			break
	if elements is False:
		return

	rows = {}
	for e in elements:
		if e.text.count(prefix) == 1 and e.text.count('Force join') == 1:
			name, rowData = ProcessTableRow(e)
			rows[name] = rowData
	return rows


def InitializeState():
	if os.path.isfile(stateFile + '.json'):
		state = ReadState()
		return state
	players = LoadFileToList(playerListFile)
	roomNames = LoadFileToList(roomListFile)
	random.shuffle(players)
	
	state = {
		'queue' : players,
		'maxQueueLength' : 2,
		'playerRoomPreference' : {},
		'rooms' : {name : {
			'name' : name,
			'index' : 0,
			'finished' : True,
		} for name in roomNames},
	}
	WriteState(state)
	return state


def PrintState(state):
	runningRooms = [data for name, data in state['rooms'].items() if not data['finished']]
	for room in runningRooms:
		print('Running: "{}": {} vs {}'.format(
			room['createdName'], room['players'][0], room['players'][1]))
	print('Queue: {}'.format(state['queue']))


def FindRoomForPlayers(state, players):
	checkRooms = []
	for name in players:
		if name in state['playerRoomPreference']:
			checkRooms.append(state['playerRoomPreference'][name])
	checkRooms = checkRooms + list(state['rooms'].keys())
	
	for room in checkRooms:
		if state['rooms'][room]['finished']:
			state['rooms'][room]['finished'] = False
			return state['rooms'][room]
	return False


def MakeRooms(driver, roomsToMake):
	roomStr = ''
	first = True
	for name, data in roomsToMake.items():
		if first:
			first = False
		else:
			roomStr = roomStr + '//'
		roomStr = roomStr + '{},{},{}'.format(name, data[0], data[1])
	massRoomField = driver.find_element(By.NAME,'battleList')
	massRoomField.clear()
	massRoomField.send_keys(roomStr)
	
	createBattles = driver.find_element(
		By.XPATH,
		'//input[@type="submit" and @value="Create Battles" and contains(@class, "js_confirm")]')
	createBattles.click()
	alert = Alert(driver)
	alert.accept()
	
	joinAttempts = {name : 0 in roomsToMake.keys()}
	tryForceJoin = True
	while tryForceJoin:
		driver.implicitly_wait(0.5)
		tryForceJoin = False
		rows = GetRoomTable(driver)
		for name, rowData in rows.items():
			if name in roomsToMake:
				if 'forceJoin' in rowData and not rowData['playersJoined'] and joinAttempts[name] < 4:
					print('Force joining', name)
					rowData['forceJoin'].click()
					joinAttempts[name] = joinAttempts[name] + 1
					driver.implicitly_wait(0.5 * joinAttempts[name])
					tryForceJoin = True
					break
	return {n : (v < 4) for n, v in joinAttempts.items()}


def SetupRequiredRooms(driver, state):
	rooms = {}
	while len(state['queue']) > state['maxQueueLength']:
		room = FindRoomForPlayers(state, state['queue'][:2])
		room['index'] = room['index'] + 1
		room['players'] = state['queue'][:2]
		room['createdName'] = '{}{} {}'.format(prefix, room['name'], room['index'])
		rooms[room['createdName']] = state['queue'][:2]
		state['queue'] = state['queue'][2:]
		print('Adding room "{}": {} vs {}'.format(
			room['createdName'], room['players'][0], room['players'][1]))
	
	if len(rooms) > 0:
		success = MakeRooms(driver, rooms)
	return state


def HandleRoomFinish(state, room, winner=False):
	if room not in state['rooms']:
		return state
	roomData = state['rooms'][room]
	if roomData['finished']:
		return state
	
	if winner is False:
		winner = GetListInput('Who won?', roomData['players'])
	loser  = ListRemove(roomData['players'], winner)[0]
	
	roomData['finished'] = True
	state['queue'] = [winner] + state['queue'] + [loser]
	state['playerRoomPreference'][winner] = room
	state['playerRoomPreference'] = DictRemove(state['playerRoomPreference'], loser)
	return state


def GetBattleWinner(driver, battleID):
	print('Checking battle "{}"'.format(battleID))
	driver.get('https://zero-k.info/Battles/Detail/{}?ShowWinners=True'.format(battleID))
	driver.implicitly_wait(0.5)
	
	winnerBox = driver.find_element(By.CLASS_NAME, 'fleft.battle_winner')
	elements = winnerBox.find_elements(By.XPATH, ".//*")
	userNameBox = winnerBox.find_element(By.CSS_SELECTOR, "a[href^='/Users/Detail/']")
	return userNameBox.text


def UpdateGameState(driver, state):
	pageRooms = GetRoomTable(driver)
	needReturnToPage = False
	for baseName, roomData in state['rooms'].items():
		if 'createdName' in roomData and roomData['createdName'] in pageRooms:
			pageData = pageRooms[roomData['createdName']]
			if 'battleID' in pageData and (not roomData['finished']):
				winner = GetBattleWinner(driver, pageData['battleID'])
				state = HandleRoomFinish(state, baseName, winner=winner)
				needReturnToPage = True
	
	if needReturnToPage:
		driver.get('https://zero-k.info/Tourney')
		driver.implicitly_wait(0.5)
	return state

state  = InitializeState()
driver = InitialiseWebDriver()

while True:
	print('========== Updates ==========')
	state = UpdateGameState(driver, state)
	state = SetupRequiredRooms(driver, state)
	
	print('=========== State ===========')
	PrintState(state)
	
	#time.sleep(10)
	WriteState(state)
	input('Press enter')
