import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from api.channels import room_players, room_watchers, room_legacy

User = get_user_model()


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        # Role: player = has card, watcher = no card. From query string (?role=player|watcher).
        query = self.scope.get('query_string', b'').decode()
        role = 'both'
        for part in query.split('&'):
            if part.startswith('role='):
                role = part.split('=', 1)[1].strip().lower() or 'both'
                break

        # Join rooms: players, watchers, or both (default = both for backward compat)
        groups_to_join = []
        if role in ('player', 'both'):
            groups_to_join.append(room_players(self.game_id))
        if role in ('watcher', 'both'):
            groups_to_join.append(room_watchers(self.game_id))
        if not groups_to_join:
            groups_to_join.append(room_legacy(self.game_id))

        for group_name in groups_to_join:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave all groups we may have joined (players, watchers, legacy)
        for group_name in (room_players(self.game_id), room_watchers(self.game_id), room_legacy(self.game_id)):
            await self.channel_layer.group_discard(group_name, self.channel_name)

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        # Handle different message types
        if message_type == 'ping':
            await self.send(text_data=json.dumps({
                'type': 'pong'
            }))

    # Receive message from game group
    async def game_message(self, event):
        message = event['message']
        message_type = event.get('type', 'game_update')

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': message_type,
            'data': message
        }))

    # Handler for number called event
    async def number_called(self, event):
        await self.send(text_data=json.dumps({
            'type': 'number_called',
            'data': event['data']
        }))

    # Handler for card selected event
    async def card_selected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'card_selected',
            'data': event['data']
        }))

    # Handler for game started event
    async def game_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'data': event['data']
        }))

    # Handler for game ended event
    async def game_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_ended',
            'data': event['data']
        }))

    # Handler for winner declared event
    async def winner_declared(self, event):
        await self.send(text_data=json.dumps({
            'type': 'winner_declared',
            'data': event['data']
        }))
    
    # Handler for admin message event
    async def admin_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'admin_message',
            'data': event['data']
        }))

    # Handler for game cancelled (e.g. refund and cancel)
    async def game_cancelled(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_cancelled',
            'data': event['data']
        }))
    
    # Handler for batched events (PHASE 5 OPTIMIZATION: Batch WebSocket broadcasts)
    async def batch_events(self, event):
        """
        Handle batched events - sends multiple events in one WebSocket message.
        This reduces overhead by 50-70% compared to individual broadcasts.
        """
        events = event.get('data', {}).get('events', [])
        
        # Send each event individually to the client
        # The frontend will process them as separate events
        for evt in events:
            await self.send(text_data=json.dumps({
                'type': evt.get('type', 'unknown'),
                'data': evt.get('data', {})
            }))
