class Animal:
    def __init__(self, name):
        self.name = name

    def speak(self):
        return "..."

    def introduce(self):
        return f"{self.name}: {self.speak()}"


class Dog(Animal):
    def __init__(self, name):
        super().__init__(name)
        self.tricks = []

    def speak(self):
        return "멍멍"

    def learn(self, trick):
        self.tricks.append(trick)
        return self.introduce()


def make_dog(name):
    dog = Dog(name)
    dog.learn("앉아")
    return dog


if __name__ == "__main__":
    pet = make_dog("초코")
    animal = Animal("동물")
    print(animal.speak())
