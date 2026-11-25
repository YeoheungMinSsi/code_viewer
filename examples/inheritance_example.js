class Animal {
  constructor(name) {
    this.name = name;
  }

  speak() {
    return "...";
  }

  introduce() {
    return `${this.name}: ${this.speak()}`;
  }
}

class Dog extends Animal {
  constructor(name) {
    super(name);
    this.tricks = [];
  }

  speak() {
    return "멍멍";
  }

  learn(trick) {
    this.tricks.push(trick);
    return this.introduce();
  }
}

function makeDog(name) {
  const dog = new Dog(name);
  dog.learn("앉아");
  return dog;
}

const pet = makeDog("초코");
const animal = new Animal("동물");
console.log(animal.speak());
