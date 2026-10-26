import json

from django.test import RequestFactory, TestCase
from django.utils import timezone

from .models import LotteryHeldNumber, LotteryItem, LotteryPurchase, LotterySettings, LotteryWinner, User
from . import lottery_views
from telegram_bot.receipt_messages import _winner_lines


class QuickFixTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            username='quickfix_admin', password='x', is_staff=True,
        )
        self.item = LotteryItem.objects.create(
            name='Quick Fix Round',
            total_tickets=100,
            draw_mode=LotteryItem.DRAW_MODE_MANUAL,
            is_active=True,
            automatic_announcement=True,
            prizes=[{'place': '1st', 'title': 'First', 'amount': 1000}],
        )
        self.settings = LotterySettings.get_settings()

    def _post(self, view, payload):
        request = self.factory.post(
            '/admin-dashboard/test/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        request.user = self.admin
        return view(request)

    def _purchase(self, phone, numbers, status='verified', name='Buyer', provider='telebirr', user=None):
        return LotteryPurchase.objects.create(
            user=user,
            lottery_item=self.item,
            full_name=name,
            phone=phone,
            numbers=numbers,
            quantity=len(numbers),
            amount=0,
            receipt_hash=f'hash-{phone}-{numbers}-{timezone.now().timestamp()}',
            payment_provider=provider,
            status=status,
        )

    def test_item_clear_timer_save(self):
        self.item.ends_at = timezone.now()
        self.item.save(clear_timer=True)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.ends_at)

    def test_bulk_hold_is_all_or_nothing_and_reports_free(self):
        self._purchase('0911000010', [10])
        before = LotteryHeldNumber.objects.count()
        response = self._post(lottery_views.lottery_held_numbers_admin, {
            'action': 'bulk',
            'lottery_item_id': self.item.id,
            'numbers': '10, 11',
            'phone': '0911222333',
            'name': 'Walk in',
        })
        self.assertEqual(response.status_code, 409)
        body = json.loads(response.content)
        self.assertEqual(body['taken'], [10])
        self.assertEqual(body['free'], [11])
        self.assertEqual(LotteryHeldNumber.objects.count(), before)

        response = self._post(lottery_views.lottery_held_numbers_admin, {
            'action': 'bulk',
            'lottery_item_id': self.item.id,
            'numbers': '11, 12',
            'phone': '0911222333',
            'name': 'Walk in',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(LotteryHeldNumber.objects.filter(lottery_item=self.item).values_list('number', flat=True)),
            [11, 12],
        )

    def test_lookup_and_announce_uses_ticket_holder_not_entered_phone(self):
        buyer_a = User.objects.create(username='buyer_a', phone_number='0911000001', first_name='A')
        buyer_b = User.objects.create(username='buyer_b', phone_number='0911000002', first_name='B')
        self._purchase('0911000001', [1], user=buyer_a)
        self._purchase('0911000002', [2], user=buyer_b)
        LotteryHeldNumber.objects.create(
            lottery_item=self.item, number=3, phone='0911000003', name='Walk-in C',
        )

        response = self._post(lottery_views.lottery_winner_lookup, {
            'lottery_item_id': self.item.id,
            'ticket_number': 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['found'])

        response = self._post(lottery_views.lottery_announce_item_winner, {
            'lottery_item_id': self.item.id,
            'notify_users': False,
            'winners': [
                {'winning_ticket': 1, 'phone': '0999999999', 'prize_name': '1st'},
                {'winning_ticket': 2, 'phone': '0999999999', 'prize_name': '2nd'},
                {'winning_ticket': 3, 'phone': '0999999999', 'prize_name': '3rd'},
            ],
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            sorted(LotteryWinner.objects.filter(lottery_item=self.item).values_list('phone', flat=True)),
            ['0911000001', '0911000002', '0911000003'],
        )
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_active)
        self.assertFalse(LotteryHeldNumber.objects.filter(lottery_item=self.item).exists())

    def test_pending_ticket_cannot_be_announced(self):
        self._purchase('0911000004', [4], status='pending')
        response = self._post(lottery_views.lottery_announce_item_winner, {
            'lottery_item_id': self.item.id,
            'notify_users': False,
            'winners': [{'winning_ticket': 4, 'phone': '0911000004'}],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)['error_code'], 'ticket_pending')

    def test_winner_lines_show_phone_not_name(self):
        lines = _winner_lines([
            {'order': 1, 'prize': 'First', 'number': 1, 'phone': '0911000001', 'name': 'Secret Name'}
        ])
        self.assertIn('0911000001', lines[0])
        self.assertNotIn('Secret Name', lines[0])
