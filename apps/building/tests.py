from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rooms.models import Room

from .models import Building

User = get_user_model()


class BuildingRoomsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='viewer', password='test-pass-123')
        cls.main = Building.objects.create(code='B1', name='Main Building')
        cls.annex = Building.objects.create(code='B2', name='Annex Building')
        cls.lab = Room.objects.create(
            building=cls.main, room_name='Lab 1', room_type='Laboratory', capacity=40,
        )
        cls.room = Room.objects.create(
            building=cls.main, room_name='Room 101', capacity=30,
        )
        cls.annex_room = Room.objects.create(
            building=cls.annex, room_name='Annex Lab', room_type='Laboratory', capacity=25,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def rooms_url(self, building):
        return reverse('building:building_rooms', args=[building.id])

    def test_rooms_page_lists_only_that_buildings_rooms(self):
        response = self.client.get(self.rooms_url(self.main))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Room 101')
        self.assertContains(response, 'Lab 1')
        self.assertNotContains(response, 'Annex Lab')

    def test_room_search_stays_within_the_building(self):
        response = self.client.get(self.rooms_url(self.main), {'q': 'lab'})
        self.assertContains(response, 'Lab 1')
        self.assertNotContains(response, 'Room 101')
        self.assertNotContains(response, 'Annex Lab')

    def test_building_search_matches_room_names(self):
        response = self.client.get(reverse('building:building_list'), {'q': 'Annex Lab'})
        self.assertContains(response, 'Annex Building')
        self.assertNotContains(response, 'Main Building')

    def test_rooms_button_passes_the_search_to_the_building_page(self):
        response = self.client.get(reverse('building:building_list'), {'q': 'Lab 1'})
        self.assertContains(response, f"{self.rooms_url(self.main)}?q=Lab")
        self.assertNotContains(response, 'Annex Building')

    def test_unknown_building_returns_404(self):
        response = self.client.get(reverse('building:building_rooms', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_standalone_rooms_page_redirects_to_buildings(self):
        response = self.client.get(reverse('rooms:room_list'))
        self.assertRedirects(response, reverse('building:building_list'))
