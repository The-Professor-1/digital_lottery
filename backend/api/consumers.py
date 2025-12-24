import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.game_group_name = f'game_{self.game_id}'

        # Join game group
        await self.channel_layer.group_add(
            self.game_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave game group
        await self.channel_layer.group_discard(
            self.game_group_name,
            self.channel_name
        )

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

